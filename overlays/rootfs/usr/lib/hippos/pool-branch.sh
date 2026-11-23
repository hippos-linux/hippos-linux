pool_branch_mode() {
    if findmnt -n -o OPTIONS -T "$1" 2>/dev/null | tr ',' '\n' | grep -qx ro; then
        echo RO
    else
        echo RW
    fi
}

share_saves_dirs() {
    find "$1" -mindepth 1 -maxdepth 2 -type d -iname saves -print0 2>/dev/null
}

add_alias_branches() {
    local alias_root="$1" alias_mode="$2"
    shift 2
    rm -rf "${alias_root}"
    local branch source target mode index=0
    for branch in "${external_branches[@]}"; do
        mode="${alias_mode}"
        [[ "${mode}" == inherit ]] && mode="$(pool_branch_mode "${branch}")"
        while read -r source target; do
            [[ -z "${source}" || "${source}" == '#'* || ! -d "${branch}/${source}" ]] && continue
            index=$((index + 1))
            mkdir -p "$(dirname "${alias_root}/${index}/${target}")"
            ln -s "${branch}/${source}" "${alias_root}/${index}/${target}"
            branches="${branches}:${alias_root}/${index}=${mode}"
            log "${branch}/${source} appears as ${target}"
        done < <(cat "$@")
    done
}

update_pool_branches() {
    local pool="$1" wanted="$2" current
    if ! current="$(python3 -c 'import os, sys; print(os.getxattr(sys.argv[1], "user.mergerfs.branches").decode())' "${pool}/.mergerfs" 2>/dev/null)"; then
        log "${pool} is not a mergerfs pool; branches left as they are"
        return 0
    fi
    if [[ "${current}" == "${wanted}" ]]; then
        log "branches unchanged"
        return 0
    fi
    python3 -c 'import os, sys; os.setxattr(sys.argv[1], "user.mergerfs.branches", sys.argv[2].encode())' "${pool}/.mergerfs" "${wanted}"
    log "branches updated: ${wanted}"
}
