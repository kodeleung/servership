#!/usr/bin/env bash
install_caddy() {
    require_root
    detect_platform
    if package_installed caddy || command -v caddy >/dev/null; then
        caddy version
        require_service caddy
        return 10
    fi
    prepare_repo_tools
    local work
    work=$(mktemp -d)
    # Freeze the local path now; it leaves scope when the installer returns.
    # shellcheck disable=SC2064
    trap "$(printf 'rm -rf -- %q' "$work")" EXIT
    curl --fail --silent --show-error --location --proto '=https' https://dl.cloudsmith.io/public/caddy/stable/gpg.key -o "$work/key.asc"
    gpg --batch --dearmor -o "$work/key.gpg" "$work/key.asc"
    repo_file "$work/key.gpg" /usr/share/keyrings/caddy-stable-archive-keyring.gpg
    curl --fail --silent --show-error --location --proto '=https' https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt -o "$work/caddy.list"
    repo_file "$work/caddy.list" /etc/apt/sources.list.d/servership-caddy.list
    apt-get update
    apt_install caddy
    caddy version
    systemctl enable --now caddy
    require_service caddy
}
