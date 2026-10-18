# /etc/profile.d/command_audit.sh
# Logs every bash command with user, IP, and timestamp.
# The file /var/log/commands_audit.log is tailed by server-monitor.py.

touch /var/log/commands_audit.log
chmod 600 /var/log/commands_audit.log

__audit_cmd() {
    local cmd
    cmd=$(HISTTIMEFORMAT="" history 1 2>/dev/null | sed 's/^ *[0-9]* *//')
    # skip empty and the audit function itself
    [ -z "$cmd" ] && return
    case "$cmd" in
        __audit_cmd*|clear*|exit*|logout*|'') return ;;
    esac
    local ip="${SSH_CLIENT%% *}"
    [ -z "$ip" ] && ip="local"
    echo "$(date '+%Y-%m-%d %H:%M:%S')|$(whoami)|${ip}|${cmd}" >> /var/log/commands_audit.log
}

# prepend to any existing PROMPT_COMMAND
if [ -n "$PROMPT_COMMAND" ]; then
    export PROMPT_COMMAND="__audit_cmd; $PROMPT_COMMAND"
else
    export PROMPT_COMMAND="__audit_cmd"
fi

export HISTTIMEFORMAT="%F %T "
export HISTSIZE=10000
export HISTFILESIZE=50000
