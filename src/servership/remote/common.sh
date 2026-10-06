#!/usr/bin/env bash
# Shared only by packaged remote scripts; never executes on import.
require_root() { [[ $EUID -eq 0 ]] || { echo '需要 root 权限' >&2; return 1; }; }
package_installed() { [[ $(dpkg-query -W -f='${Status}' "$1" 2>/dev/null) == 'install ok installed' ]]; }
apt_install() {
    DEBIAN_FRONTEND=noninteractive apt-get -y --no-upgrade -o Dpkg::Options::=--force-confold install "$@"
}
require_service() { systemctl is-active --quiet "$1"; }

detect_platform() {
    # shellcheck source=/dev/null
    source /etc/os-release
    DIST_ID=${ID:-}
    DIST_CODENAME=${VERSION_CODENAME:-}
    case "$DIST_ID:${VERSION_ID:-}" in
        debian:12|debian:13|ubuntu:22.04|ubuntu:24.04|ubuntu:26.04) ;;
        *) echo '不支持此发行版本' >&2; return 1;;
    esac
    DIST_ARCH=$(dpkg --print-architecture)
    case "$DIST_ARCH" in amd64|arm64) ;; *) echo '首版支持 amd64 / arm64' >&2; return 1;; esac
    [[ -n $DIST_CODENAME ]]
}

prepare_repo_tools() {
    apt-get update
    apt_install ca-certificates curl gnupg
    install -d -m 755 /etc/apt/keyrings
}

# Never replace a repository/key file that existed before this run.
repo_file() {
    local source=$1 target=$2
    [[ ! -L $target ]] || { echo "软件源文件是符号链接：$target" >&2; return 1; }
    if [[ -e $target ]]; then
        cmp -s "$source" "$target" || { echo "已有不同的软件源文件，保留原配置：$target" >&2; return 1; }
    else
        install -m 644 "$source" "$target"
    fi
}

apt_install_block_services() (
    # Debian package hooks honor policy-rc.d. Do not replace an existing policy.
    local policy=/usr/sbin/policy-rc.d
    if [[ -e $policy || -L $policy ]]; then
        echo '已有 policy-rc.d，无法保证安装不启动/重启服务；保留原策略' >&2
        return 1
    fi
    (set -o noclobber; printf '#!/bin/sh\nexit 101\n' > "$policy")
    chmod 755 "$policy"
    trap 'rm -f -- "$policy"' EXIT
    trap 'exit 130' INT
    trap 'exit 143' TERM
    apt_install "$@"
)
