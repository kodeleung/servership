#!/usr/bin/env bash
# Shared only by packaged remote scripts; never executes on import.
require_root() { [[ $EUID -eq 0 ]] || { echo '需要 root 权限' >&2; return 1; }; }
package_installed() { [[ $(dpkg-query -W -f='${Status}' "$1" 2>/dev/null) == 'install ok installed' ]]; }
apt_install() {
    DEBIAN_FRONTEND=noninteractive apt-get -y --no-upgrade -o Dpkg::Options::=--force-confold install "$@"
}
require_service() { systemctl is-active --quiet "$1"; }
