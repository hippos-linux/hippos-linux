case "$-" in
    *i*) ;;
    *) return ;;
esac

if [ -z "${HIPPOS_LOGIN_BANNER_SHOWN:-}" ]; then
    export HIPPOS_LOGIN_BANNER_SHOWN=1
    printf '\033c'
    if command -v fastfetch >/dev/null 2>&1; then
        fastfetch
    fi
fi

if mountpoint -q /userdata 2>/dev/null; then
    cd /userdata
fi

export PS1='\[\e]2;HippOS - $PWD\a\][\u@\h $(p=${PWD/#"$HOME"/~};((${#p}>30))&&echo "${p::10}…${p:(-19)}"||echo "\w")]\$ '

export HISTCONTROL=ignoredups
export HISTSIZE=1000

alias ls='ls --color=auto'
alias ll='ls -lah'
