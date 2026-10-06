#!/usr/bin/env bash
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo 'Root privileges required' >&2; exit 1; }
# shellcheck source=/dev/null
source /etc/os-release
case ${ID:-} in debian|ubuntu) ;; *) echo 'Only Debian / Ubuntu are supported' >&2; exit 1;; esac
for tool in apt-get dpkg-query systemctl getent ssh-keygen awk stat install mktemp; do
    command -v "$tool" >/dev/null || { echo "Missing server tool: $tool" >&2; exit 1; }
done
[[ -d /run/systemd/system ]] || { echo 'The server must be running systemd' >&2; exit 1; }
echo "System check complete: $ID ${VERSION_ID:-}; root privileges obtained"
