#!/usr/bin/env bash
set -e
cd -- "$(dirname -- "$(readlink -f -- "$0")")"
if [[ -x .venv/bin/python ]]; then
    exec .venv/bin/python luma.py "$@"
fi
exec /usr/bin/python3 luma.py "$@"
