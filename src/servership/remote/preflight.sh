#!/usr/bin/env bash
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo '需要 root 权限' >&2; exit 1; }
source /etc/os-release
case ${ID:-} in debian|ubuntu) ;; *) echo '仅支持 Debian / Ubuntu' >&2; exit 1;; esac
for tool in apt-get dpkg-query systemctl getent ssh-keygen awk stat install mktemp; do
    command -v "$tool" >/dev/null || { echo "缺少服务器工具：$tool" >&2; exit 1; }
done
[[ -d /run/systemd/system ]] || { echo '服务器需要运行 systemd' >&2; exit 1; }
echo "系统检查完成：$ID ${VERSION_ID:-}；root 权限已取得"
