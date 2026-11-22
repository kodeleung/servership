#!/usr/bin/env bash
install_tailscale() {
    require_root
    detect_platform
    if command -v tailscale >/dev/null || package_installed tailscale; then
        tailscale version
        require_service tailscaled
        return 10
    fi
    prepare_repo_tools
    local work
    work=$(mktemp -d)
    # Freeze the local path now; it leaves scope when the installer returns.
    # shellcheck disable=SC2064
    trap "$(printf 'rm -rf -- %q' "$work")" EXIT
    curl --fail --silent --show-error --location --connect-timeout 15 --max-time 120 --proto '=https' "https://pkgs.tailscale.com/stable/$DIST_ID/$DIST_CODENAME.noarmor.gpg" -o "$work/tailscale.gpg"
    repo_file "$work/tailscale.gpg" /etc/apt/keyrings/servership-tailscale.gpg
    printf 'Types: deb\nURIs: https://pkgs.tailscale.com/stable/%s\nSuites: %s\nComponents: main\nSigned-By: /etc/apt/keyrings/servership-tailscale.gpg\n' "$DIST_ID" "$DIST_CODENAME" > "$work/tailscale.sources"
    repo_file "$work/tailscale.sources" /etc/apt/sources.list.d/servership-tailscale.sources
    apt-get update
    apt_install tailscale
    systemctl enable --now tailscaled
    tailscale version
    require_service tailscaled
}
