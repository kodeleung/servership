#!/usr/bin/env bash
set -uo pipefail
base=$(dirname "${BASH_SOURCE[0]}")
# shellcheck source=common.sh
source "$base/common.sh"
require_root || exit 1
report=${1:?结果路径缺失}
user=${2:?账号缺失}
shift 2
[[ $user =~ ^[a-zA-Z_][a-zA-Z0-9_.-]*\$?$ ]] || exit 1
[[ ! -e $report && ! -L $report ]] || { echo '拒绝覆盖结果文件' >&2; exit 1; }
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
    echo "安装检查：$software"
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
        0) status=success; detail='已安装并验证';;
        10) status=skipped; detail='已满足，保留现有安装';;
        *) status=failed; detail="安装或验证失败（$code），详见终端输出"; failed=1;;
    esac
    if [[ $software == sing-box && $code == 0 ]]; then detail='已安装，待配置（未启动服务）'; fi
    printf '%s\t%s\t%s\n' "$software" "$status" "$detail" >> "$report"
done
exit "$failed"
