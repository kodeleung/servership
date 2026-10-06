#!/usr/bin/env bash
install_openssh() {
    require_root
    detect_platform
    if package_installed openssh-server; then
        /usr/sbin/sshd -t
        require_service ssh
        return 10
    fi
    if [[ -e /etc/ssh/sshd_config ]] || command -v sshd >/dev/null; then
        echo '已有未托管的 SSH 配置或服务，保留原状态' >&2
        return 1
    fi
    apt-get update
    apt_install_block_services openssh-server
    install -d -m 755 /run/sshd
    /usr/sbin/sshd -t
    systemctl enable --now ssh
    require_service ssh
}
