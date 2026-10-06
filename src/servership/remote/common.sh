#!/usr/bin/env bash
# Shared only by packaged remote scripts; never executes on import.
require_root() { [[ $EUID -eq 0 ]] || { echo 'Root privileges required' >&2; return 1; }; }
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
        *) echo 'Unsupported distribution version' >&2; return 1;;
    esac
    DIST_ARCH=$(dpkg --print-architecture)
    case "$DIST_ARCH" in amd64|arm64) ;; *) echo 'Supported architectures: amd64 / arm64' >&2; return 1;; esac
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
    [[ ! -L $target ]] || { echo "Repository file is a symbolic link: $target" >&2; return 1; }
    if [[ -e $target ]]; then
        cmp -s "$source" "$target" || { echo "A different repository file already exists; preserving the configuration: $target" >&2; return 1; }
    else
        install -m 644 "$source" "$target"
    fi
}

apt_install_block_services() (
    # Debian package hooks honor policy-rc.d. Do not replace an existing policy.
    local policy=/usr/sbin/policy-rc.d
    if [[ -e $policy || -L $policy ]]; then
        echo 'Existing policy-rc.d prevents guaranteeing installation without service starts/restarts; preserving the policy' >&2
        return 1
    fi
    (set -o noclobber; printf '#!/bin/sh\nexit 101\n' > "$policy")
    chmod 755 "$policy"
    trap 'rm -f -- "$policy"' EXIT
    trap 'exit 130' INT
    trap 'exit 143' TERM
    apt_install "$@"
)
