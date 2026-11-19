#!/usr/bin/env bash
# Create .env for local development from .env.example, replacing every
# __GENERATE__ / __GENERATE_PASSWORD__ placeholder with a fresh random value. Refuses to overwrite
# an existing .env. Development only; values never leave this machine.
set -euo pipefail
umask 077  # .env holds secrets: never readable by other users, not even briefly

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
example="$root/.env.example"
target="$root/.env"

if [[ -e "$target" ]]; then
    echo ".env already exists; not overwritten." >&2
    exit 1
fi

random_hex() { od -An -N16 -tx1 /dev/urandom | tr -d ' \n'; }

tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT
while IFS= read -r line || [[ -n "$line" ]]; do
    while [[ "$line" == *__GENERATE_PASSWORD__* ]]; do
        # Upper, lower, digit and symbol, as ZITADEL's default policy requires.
        line="${line/__GENERATE_PASSWORD__/Ma-$(random_hex)-Z9!}"
    done
    while [[ "$line" == *__GENERATE__* ]]; do
        line="${line/__GENERATE__/$(random_hex)}"
    done
    printf '%s\n' "$line" >>"$tmp"
done <"$example"

# Expand ${VAR} references to keys defined earlier in the file (the database
# URLs reuse the generated passwords). Compose and SaaS-OS's .env reader do
# not both expand references, so .env gets literal values.
values=()
: >"$target"
while IFS= read -r line || [[ -n "$line" ]]; do
    if [[ "$line" =~ ^([A-Z0-9_]+)=(.*)$ ]]; then
        key="${BASH_REMATCH[1]}"
        val="${BASH_REMATCH[2]}"
        while [[ "$val" =~ \$\{([A-Z0-9_]+)\} ]]; do
            ref="${BASH_REMATCH[1]}"
            replacement=""
            for pair in "${values[@]}"; do
                [[ "${pair%%=*}" == "$ref" ]] && replacement="${pair#*=}"
            done
            val="${val//\$\{$ref\}/$replacement}"
        done
        values+=("$key=$val")
        printf '%s=%s\n' "$key" "$val" >>"$target"
    else
        printf '%s\n' "$line" >>"$target"
    fi
done <"$tmp"

chmod 600 "$target"
echo "Created .env with random local secrets. Next: docker compose up -d --build"
