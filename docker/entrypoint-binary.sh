#!/bin/sh
# Entry point for the nps-ctl binary images (Nuitka build, no Python runtime).
#
# Behaviour matches docker/entrypoint.sh; the binary lives at
# /usr/local/bin/nps-ctl.
set -eu

mkdir -p /config 2>/dev/null || true

case "${1:-}" in
    --version|-V|--help|-h)
        exec /usr/local/bin/nps-ctl "$@"
        ;;
esac

if [ "$#" -eq 0 ] || [ "${1#-}" != "$1" ]; then
    if [ ! -f /config/edges.toml ]; then
        echo "nps-ctl: /config/edges.toml not found." >&2
        echo "Mount your config directory at /config, for example:" >&2
        echo '  docker run -v "$PWD/config:/config" -p 8080:8080 oaklight/nps-ctl' >&2
        exit 1
    fi

    if [ -f /config/web-users.toml ]; then
        set -- web --host 0.0.0.0 --port 8080 \
            --users-file /config/web-users.toml "$@"
    elif [ -n "${NPS_WEB_USERNAME:-}" ]; then
        set -- web --host 0.0.0.0 --port 8080 \
            --username "$NPS_WEB_USERNAME" "$@"
    else
        echo "nps-ctl: refusing to start the dashboard without authentication." >&2
        echo "Provide /config/web-users.toml, or set NPS_WEB_USERNAME and NPS_WEB_PASSWORD." >&2
        exit 1
    fi
fi

case " $* " in
    *" --config "*) ;;
    *) set -- --config /config/edges.toml "$@" ;;
esac

exec /usr/local/bin/nps-ctl "$@"
