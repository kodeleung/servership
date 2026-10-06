#!/usr/bin/env bash
install_docker() {
    require_root
    detect_platform
    if command -v docker >/dev/null || package_installed docker-ce || package_installed docker.io; then
        docker version
        docker compose version
        require_service docker
        return 10
    fi
    local conflict
    for conflict in docker-compose docker-compose-v2 docker-doc docker-buildx podman-docker containerd runc; do
        if package_installed "$conflict"; then
            echo "已有冲突软件包，保留原安装：$conflict" >&2
            return 1
        fi
    done
    prepare_repo_tools
    local work
    work=$(mktemp -d)
    # Freeze the local path now; it leaves scope when the installer returns.
    # shellcheck disable=SC2064
    trap "$(printf 'rm -rf -- %q' "$work")" EXIT
    curl --fail --silent --show-error --location --proto '=https' "https://download.docker.com/linux/$DIST_ID/gpg" -o "$work/docker.asc"
    repo_file "$work/docker.asc" /etc/apt/keyrings/servership-docker.asc
    printf 'Types: deb\nURIs: https://download.docker.com/linux/%s\nSuites: %s\nComponents: stable\nArchitectures: %s\nSigned-By: /etc/apt/keyrings/servership-docker.asc\n' "$DIST_ID" "$DIST_CODENAME" "$DIST_ARCH" > "$work/docker.sources"
    repo_file "$work/docker.sources" /etc/apt/sources.list.d/servership-docker.sources
    apt-get update
    apt_install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    systemctl enable --now docker
    docker version
    docker compose version
    require_service docker
}
