#!/usr/bin/env bash
set -uo pipefail
base=$(dirname "${BASH_SOURCE[0]}")
# shellcheck source=common.sh
source "$base/common.sh"
require_root || exit 1
trap 'exit 130' INT
trap 'exit 143' TERM
report=${1:?Results path missing}
user=${2:?Username missing}
shift 2
[[ $user =~ ^[a-zA-Z_][a-zA-Z0-9_.-]*\$?$ ]] || exit 1
[[ ! -e $report && ! -L $report ]] || { echo 'Refusing to overwrite the results file' >&2; exit 1; }
for software in "$@"; do
    case $software in caddy|docker|sing-box|openssh) ;; *) exit 1;; esac
done
umask 077
: > "$report"
record=$(getent passwd "$user") || exit 1
IFS=: read -r _ _ uid gid _ <<< "$record"
chown "$uid:$gid" "$report" || exit 1
failed=0
for software in "$@"; do
    echo "Installation check: $software"
    printf '%s\tfailed\tExecution started but has not completed; partial changes may exist\n' "$software" >> "$report"
    # Not in an if/|| context: failures inside an installer obey errexit.
    (
        set -e
        # Module name was validated against the fixed allowlist above.
        # shellcheck disable=SC1090
        source "$base/installers/$software.sh"
        "install_${software//-/_}"
    )
    code=$?
    case $code in
        0) status=success; detail='Installed and verified';;
        10) status=skipped; detail='Already satisfied; preserving the existing installation';;
        *) status=failed; detail="Installation or verification failed ($code); see terminal output"; failed=1;;
    esac
    if [[ $software == sing-box && $code == 0 ]]; then detail='Installed; configuration required (service not started)'; fi
    updated=$(mktemp "$(dirname "$report")/result.XXXXXXXX") || exit 1
    sed '$d' "$report" > "$updated" || exit 1
    printf '%s\t%s\t%s\n' "$software" "$status" "$detail" >> "$updated"
    chmod 600 "$updated"
    chown "$uid:$gid" "$updated" || exit 1
    mv -- "$updated" "$report" || exit 1
done
exit "$failed"
