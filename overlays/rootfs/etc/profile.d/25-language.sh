_lang="$(hippos-settings get system.language 2>/dev/null)"
if [ -n "${_lang}" ]; then
    export LANG="${_lang}.UTF-8"
    export LC_ALL="${LANG}"
fi
unset _lang
