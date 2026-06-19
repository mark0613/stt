#!/bin/sh
# planning-with-files: resolve the current plan directory.
#
# Resolution order:
#   1. Newest ./.planning/<dir>/ containing task_plan.md
#   2. Otherwise empty stdout
#
# Always exits 0. Never errors out the agent loop.

set -u

PLAN_ROOT="${1:-${PWD}/.planning}"

SLUG_RE='^[A-Za-z0-9_][A-Za-z0-9._-]*$'

slug_is_valid() {
    case "$1" in
        '') return 1 ;;
    esac
    printf "%s" "$1" | grep -Eq "${SLUG_RE}"
}

# Portable mtime resolver. Tries GNU stat, BSD stat, BSD/macOS date -r,
# python3, then perl. Returns "0" on full miss so callers can sort.
mtime_of() {
    target="$1"
    out="$(stat -c '%Y' "${target}" 2>/dev/null)"
    if [ -n "${out}" ]; then printf "%s\n" "${out}"; return 0; fi
    out="$(stat -f '%m' "${target}" 2>/dev/null)"
    if [ -n "${out}" ]; then printf "%s\n" "${out}"; return 0; fi
    out="$(date -r "${target}" +%s 2>/dev/null)"
    if [ -n "${out}" ]; then printf "%s\n" "${out}"; return 0; fi
    if command -v python3 >/dev/null 2>&1; then
        out="$(python3 -c "import os,sys;print(int(os.stat(sys.argv[1]).st_mtime))" "${target}" 2>/dev/null)"
        if [ -n "${out}" ]; then printf "%s\n" "${out}"; return 0; fi
    fi
    if command -v python >/dev/null 2>&1; then
        out="$(python -c "import os,sys;print(int(os.stat(sys.argv[1]).st_mtime))" "${target}" 2>/dev/null)"
        if [ -n "${out}" ]; then printf "%s\n" "${out}"; return 0; fi
    fi
    if command -v perl >/dev/null 2>&1; then
        out="$(perl -e 'print((stat shift)[9])' "${target}" 2>/dev/null)"
        if [ -n "${out}" ]; then printf "%s\n" "${out}"; return 0; fi
    fi
    printf "0\n"
}

resolve_latest_dir() {
    [ -d "${PLAN_ROOT}" ] || return 1
    latest=""
    latest_mtime=0
    for entry in "${PLAN_ROOT}"/*/; do
        [ -d "${entry}" ] || continue
        clean="${entry%/}"
        name="$(basename "${clean}")"
        case "${name}" in
            .*) continue ;;
        esac
        slug_is_valid "${name}" || continue
        [ -f "${clean}/task_plan.md" ] || continue
        mtime="$(mtime_of "${clean}")"
        if [ "${mtime}" -gt "${latest_mtime}" ] 2>/dev/null; then
            latest_mtime="${mtime}"
            latest="${clean}"
        fi
    done
    if [ -n "${latest}" ]; then
        printf "%s\n" "${latest}"
        return 0
    fi
    return 1
}

if resolve_latest_dir; then exit 0; fi
exit 0
