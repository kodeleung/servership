#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=common.sh
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
require_root
public=${1:?Public key file missing}
user=${2:?Login username missing}
[[ $user =~ ^[a-zA-Z_][a-zA-Z0-9_.-]*\$?$ ]] || exit 1
[[ -f $public && ! -L $public ]] || exit 1
[[ $(wc -l < "$public") -eq 1 ]] || { echo 'The public key must contain exactly one line' >&2; exit 1; }
fingerprint=$(ssh-keygen -lf "$public" | awk '{print $2}')
[[ -n $fingerprint && $fingerprint != *$'\n'* ]] || exit 1
record=$(getent passwd "$user")
IFS=: read -r _ _ uid gid _ home _ <<< "$record"
[[ $home == /* && $home != / && -d $home ]] || { echo 'Invalid user home directory' >&2; exit 1; }
ancestor=$home
while [[ $ancestor != / ]]; do
    [[ ! -L $ancestor ]] || { echo 'The home directory path cannot contain symbolic links' >&2; exit 1; }
    ancestor=$(dirname "$ancestor")
done
directory=$home/.ssh
authorized=$directory/authorized_keys
[[ ! -L $directory && ! -L $authorized ]] || { echo 'Refusing to write to a symbolic link' >&2; exit 1; }
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
echo "Public key authorization configured: $user"
