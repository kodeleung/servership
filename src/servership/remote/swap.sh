#!/usr/bin/env bash
set -euo pipefail
# shellcheck source=common.sh
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

configure_swap() {
    require_root
    local swapfile=${1:-/swapfile}
    local fstab=${2:-/etc/fstab}
    local swaps=${3:-/proc/swaps}
    local target_bytes=$((2 * 1024 * 1024 * 1024))
    local fstab_line="$swapfile none swap sw 0 0"
    local active_bytes existing available fstab_status

    for tool in awk df mkswap swapon stat; do
        command -v "$tool" >/dev/null || { echo "Missing server tool: $tool" >&2; return 1; }
    done
    command -v fallocate >/dev/null || command -v dd >/dev/null || { echo 'Missing server tool: fallocate or dd' >&2; return 1; }

    active_bytes=$(awk 'NR > 1 { total += $3 * 1024 } END { print total + 0 }' "$swaps")
    if (( active_bytes >= target_bytes )); then
        echo "Swap already satisfied (${active_bytes} bytes active); preserving the existing configuration"
        return 10
    fi

    [[ ! -L $swapfile ]] || { echo 'Refusing to use a symbolic link swap file' >&2; return 1; }

    if [[ -e $swapfile ]]; then
        [[ -f $swapfile ]] || { echo "Existing $swapfile is not a regular file; preserving it" >&2; return 1; }
        existing=$(stat -c%s -- "$swapfile")
        if (( existing != target_bytes )); then
            echo "Existing $swapfile size is ${existing} bytes, not ${target_bytes}; preserving it" >&2
            return 1
        fi
    else
        available=$(df -B1 --output=avail / | awk 'NR == 2 { print $1 + 0 }')
        if (( available < target_bytes + 64 * 1024 * 1024 )); then
            echo "Insufficient free space on / for a 2G swap file (${available} bytes available)" >&2
            return 1
        fi
        # Prefer fallocate; fall back to dd when unavailable or rejected by the filesystem.
        if ! command -v fallocate >/dev/null || ! fallocate -l "$target_bytes" -- "$swapfile"; then
            rm -f -- "$swapfile"
            command -v dd >/dev/null || { echo 'Missing server tool: dd' >&2; return 1; }
            dd if=/dev/zero of="$swapfile" bs=1M count=2048 status=none
        fi
        [[ $(stat -c%s -- "$swapfile") -eq $target_bytes ]] || { echo 'Created swap file has unexpected size' >&2; rm -f -- "$swapfile"; return 1; }
    fi

    chmod 600 "$swapfile"
    if ! awk -v target="$swapfile" 'NR > 1 && $1 == target { found = 1 } END { exit found ? 0 : 1 }' "$swaps"; then
        mkswap -- "$swapfile" >/dev/null
        swapon -- "$swapfile"
    fi

    if [[ -L $fstab ]]; then
        echo "Refusing to modify a symbolic link $fstab" >&2
        return 1
    fi
    [[ -f $fstab ]] || { echo "$fstab is missing" >&2; return 1; }

    fstab_status=0
    awk -v path="$swapfile" '
        $1 == path {
            if ($2 == "none" && $3 == "swap") ok = 1
            else bad = 1
        }
        END {
            if (bad) exit 2
            if (ok) exit 0
            exit 1
        }
    ' "$fstab" || fstab_status=$?
    case $fstab_status in
        0) ;;
        1)
            if [[ -s $fstab && -n $(tail -c 1 "$fstab") ]]; then
                printf '\n' >> "$fstab"
            fi
            printf '%s\n' "$fstab_line" >> "$fstab"
            ;;
        *)
            echo "Existing $fstab swapfile entry differs; preserving it" >&2
            return 1
            ;;
    esac

    echo "2G swap configured at $swapfile"
}

# Only run when executed as a remote module, not when sourced by tests.
if [[ ${BASH_SOURCE[0]##*/} == swap.sh && ${1-} != --source-only ]]; then
    configure_swap
fi
