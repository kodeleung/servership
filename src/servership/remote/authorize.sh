#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
require_root
public=${1:?公钥文件缺失}
user=${2:?登录账号缺失}
[[ $user =~ ^[a-zA-Z_][a-zA-Z0-9_.-]*\$?$ ]] || exit 1
[[ -f $public && ! -L $public ]] || exit 1
[[ $(wc -l < "$public") -eq 1 ]] || { echo '公钥必须只有一行' >&2; exit 1; }
fingerprint=$(ssh-keygen -lf "$public" | awk '{print $2}')
[[ -n $fingerprint && $fingerprint != *$'\n'* ]] || exit 1
record=$(getent passwd "$user")
IFS=: read -r _ _ uid gid _ home _ <<< "$record"
[[ $home == /* && $home != / && -d $home ]] || { echo '无效账号家目录' >&2; exit 1; }
ancestor=$home
while [[ $ancestor != / ]]; do
    [[ ! -L $ancestor ]] || { echo '家目录路径不能包含符号链接' >&2; exit 1; }
    ancestor=$(dirname "$ancestor")
done
directory=$home/.ssh
authorized=$directory/authorized_keys
[[ ! -L $directory && ! -L $authorized ]] || { echo '拒绝写入符号链接' >&2; exit 1; }
[[ ! -e $directory || -d $directory ]] || exit 1
[[ ! -e $authorized || -f $authorized ]] || exit 1
install -d -m 700 -o "$uid" -g "$gid" "$directory"
if [[ ! -e $authorized ]]; then
    install -m 600 -o "$uid" -g "$gid" /dev/null "$authorized"
fi
chmod 600 "$authorized"
chown "$uid:$gid" "$authorized"
# OpenSSH parses authorized_keys options; compare key fingerprints, not comments.
if ! ssh-keygen -lf "$authorized" 2>/dev/null | awk '{print $2}' | grep -Fxq -- "$fingerprint"; then
    if [[ -s $authorized && -n $(tail -c 1 "$authorized") ]]; then printf '\n' >> "$authorized"; fi
    cat "$public" >> "$authorized"
fi
echo "公钥授权配置完成：$user"
