pool_branch_mode() {
    if findmnt -n -o OPTIONS -T "$1" 2>/dev/null | tr ',' '\n' | grep -qx ro; then
        echo RO
    else
        echo RW
    fi
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
