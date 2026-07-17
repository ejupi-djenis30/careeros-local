#!/bin/sh
set -eu

data_dir="${DATA_DIR:-/app/data}"
secret_file="${CAREEROS_SECRET_FILE:-${data_dir}/.secret-key}"

mkdir -p "$data_dir" "${HOME:-${data_dir}/home}" "${XDG_CONFIG_HOME:-${data_dir}/config}" "${XDG_CACHE_HOME:-${data_dir}/cache}"

# A single-installation secret is generated locally and persisted with the vault.
# Explicit SECRET_KEY always wins, which keeps CI and advanced deployments deterministic.
if [ -z "${SECRET_KEY:-}" ]; then
    if [ ! -s "$secret_file" ]; then
        umask 077
        temporary_secret="${secret_file}.tmp.$$"
        python -c "import secrets; print(secrets.token_hex(32))" > "$temporary_secret"
        mv "$temporary_secret" "$secret_file"
    fi
    SECRET_KEY="$(tr -d '\r\n' < "$secret_file")"
    export SECRET_KEY
fi

python -m backend.pre_start
alembic upgrade head

exec "$@"
