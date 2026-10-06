#!/usr/bin/env bash
install_sing_box() {
    require_root
    detect_platform
    if command -v sing-box >/dev/null || package_installed sing-box; then
        sing-box version
        return 10
    fi
    prepare_repo_tools
    local work
    work=$(mktemp -d)
    # Freeze the local path now; it leaves scope when the installer returns.
    # shellcheck disable=SC2064
    trap "$(printf 'rm -rf -- %q' "$work")" EXIT
    curl --fail --silent --show-error --location --connect-timeout 15 --max-time 120 --proto '=https' https://deb.sagernet.org/gpg.key -o "$work/sagernet.asc"
    repo_file "$work/sagernet.asc" /etc/apt/keyrings/servership-sagernet.asc
    printf 'Types: deb\nURIs: https://deb.sagernet.org/\nSuites: *\nComponents: *\nEnabled: yes\nSigned-By: /etc/apt/keyrings/servership-sagernet.asc\n' > "$work/sagernet.sources"
    repo_file "$work/sagernet.sources" /etc/apt/sources.list.d/servership-sagernet.sources
    apt-get update
    apt_install_block_services sing-box
    sing-box version
}
