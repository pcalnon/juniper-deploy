#!/usr/bin/env bash
###########################################################################################################################################################################################################
# prepare_secrets.bash — Populate ./secrets/*.txt from .env.secrets.enc
#
# Replaces the previous `touch`-only behavior of `make prepare-secrets`, which
# left every file empty and silently broke worker → cascor auth (and any other
# secret-mounted service). When the canonical encrypted bundle (.env.secrets.enc)
# is decryptable on this host, each KEY=VALUE entry is written into the
# corresponding ./secrets/<file>.txt mount source so docker-compose's bind
# mounts (juniper_cascor_api_keys, cascor_auth_token, juniper_cascor_api_key,
# canopy_api_key, juniper_data_api_keys, grafana_admin_password,
# alertmanager_smtp_password) get the real values.
#
# When the bundle is missing or undecryptable on this host (e.g., first-time
# clone without the SOPS age key), the script falls back to touching empty
# placeholder files so `docker compose config` still parses — matching the
# legacy behavior but emitting a loud WARNING so operators are aware they're
# running with empty secrets.
#
# Idempotent: re-running with the same encrypted bundle yields the same file
# contents. Files are written with mode 0600.
###########################################################################################################################################################################################################
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "${SCRIPT_DIR}")"
SECRETS_DIR="${REPO_DIR}/secrets"
ENV_SECRETS_ENC="${REPO_DIR}/.env.secrets.enc"

mkdir -p "${SECRETS_DIR}"

# Mapping: <env-var-name> <secret-file-basename> <format>
# Keep in sync with docker-compose.yml `secrets:` block and the Makefile
# SECRETS_FILES list.
#
# Format values:
#   raw       — write the env var's value verbatim. Use for single-key files
#               consumed as a string (e.g., cascor_auth_token, grafana password).
#   json-list — wrap the value in a JSON array: ``["VALUE"]``. Use for files
#               consumed as a ``list[str]`` by pydantic-settings, which auto-
#               deserialises JSON for list-typed fields. juniper_cascor_api_keys
#               is the canonical list-typed secret (PR pcalnon/juniper-deploy#91
#               flipped the placeholder from ``CHANGE_BEFORE_PRODUCTION_USE``
#               to ``["CHANGE_BEFORE_PRODUCTION_USE"]`` for exactly this
#               reason — a bare string crashes cascor with
#               ``list_type`` ValidationError on startup).
declare -a MAPPINGS=(
    "JUNIPER_DATA_API_KEYS juniper_data_api_keys.txt raw"
    "JUNIPER_CASCOR_API_KEYS juniper_cascor_api_keys.txt json-list"
    "JUNIPER_CASCOR_API_KEY juniper_cascor_api_key.txt raw"
    "CASCOR_AUTH_TOKEN cascor_auth_token.txt raw"
    "CANOPY_API_KEY canopy_api_key.txt raw"
    "GRAFANA_ADMIN_PASSWORD grafana_admin_password.txt raw"
    "ALERTMANAGER_SMTP_PASSWORD alertmanager_smtp_password.txt raw"
)

# Wrap a single value in a JSON string-array literal. We escape the two
# characters that would invalidate the JSON string body (`\` and `"`) so a
# real-world token containing either is still emitted as a parseable list.
json_list_singleton() {
    local value="$1"
    # Escape backslash first, then double-quote.
    value="${value//\\/\\\\}"
    value="${value//\"/\\\"}"
    printf '["%s"]' "${value}"
}

touch_empty_placeholders() {
    for mapping in "${MAPPINGS[@]}"; do
        # shellcheck disable=SC2086
        set -- ${mapping}
        local file="${SECRETS_DIR}/$2"
        if [[ ! -f "${file}" ]]; then
            touch "${file}"
        fi
    done
}

if [[ ! -f "${ENV_SECRETS_ENC}" ]]; then
    echo "WARNING: ${ENV_SECRETS_ENC} not found — touching empty placeholders"
    touch_empty_placeholders
    exit 0
fi

if ! command -v sops >/dev/null 2>&1; then
    echo "WARNING: sops not installed — cannot decrypt ${ENV_SECRETS_ENC}; touching empty placeholders"
    touch_empty_placeholders
    exit 0
fi

PLAIN_TMP="$(mktemp)"
trap 'rm -f "${PLAIN_TMP}"' EXIT

if ! sops --input-type dotenv --output-type dotenv -d "${ENV_SECRETS_ENC}" > "${PLAIN_TMP}" 2>/dev/null; then
    echo "WARNING: failed to decrypt ${ENV_SECRETS_ENC} (no SOPS age key on this host?) — touching empty placeholders"
    touch_empty_placeholders
    exit 0
fi

# Source the plaintext so each env var is set in this shell.
set -a
# shellcheck disable=SC1090
source "${PLAIN_TMP}"
set +a

populated=0
empty=0
for mapping in "${MAPPINGS[@]}"; do
    # shellcheck disable=SC2086
    set -- ${mapping}
    var="$1"
    file="${SECRETS_DIR}/$2"
    fmt="${3:-raw}"
    value="${!var:-}"
    if [[ -z "${value}" || "${value}" == "CHANGE_BEFORE_PRODUCTION_USE" ]]; then
        : > "${file}"
        chmod 0600 "${file}"
        empty=$(( empty + 1 ))
    else
        case "${fmt}" in
            json-list)
                json_list_singleton "${value}" > "${file}"
                ;;
            raw|*)
                printf '%s' "${value}" > "${file}"
                ;;
        esac
        chmod 0600 "${file}"
        populated=$(( populated + 1 ))
    fi
done

echo "prepare-secrets: populated=${populated} placeholder/empty=${empty} from ${ENV_SECRETS_ENC}"
