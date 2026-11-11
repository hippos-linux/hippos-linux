pool_branch_mode() {
    if findmnt -n -o OPTIONS -T "$1" 2>/dev/null | tr ',' '\n' | grep -qx ro; then
        echo RO
    else
        echo RW
    fi
}
