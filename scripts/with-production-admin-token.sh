#!/usr/bin/env bash
set -euo pipefail

secret_file="${FIN_OPS_LOCAL_ADMIN_TOKEN_ENV:-$HOME/.config/fin-ops-platform/admin-token.env}"

usage() {
  cat <<'USAGE' >&2
Usage:
  scripts/with-production-admin-token.sh --store
  scripts/with-production-admin-token.sh --require-bearer <command> [args...]
  scripts/with-production-admin-token.sh <command> [args...]

Loads the local production admin token for Codex-run production validation.
Default secret file: ~/.config/fin-ops-platform/admin-token.env
USAGE
}

quote_for_shell() {
  printf "%q" "$1"
}

store_token() {
  mkdir -p "$(dirname "$secret_file")"
  printf "Paste admin token (input hidden), then press Enter: " >&2
  restore_echo() { stty echo 2>/dev/null || true; }
  trap restore_echo INT TERM EXIT
  stty -echo
  IFS= read -r token
  stty echo
  trap - INT TERM EXIT
  printf "\n" >&2
  if [[ -z "$token" ]]; then
    echo "Empty admin token; not writing $secret_file." >&2
    exit 2
  fi

  umask 077
  {
    printf "FIN_OPS_HTTP_SLO_ADMIN_TOKEN=%s\n" "$(quote_for_shell "$token")"
    printf "FIN_OPS_E2E_ADMIN_TOKEN=%s\n" "$(quote_for_shell "$token")"
  } >"$secret_file"
  chmod 600 "$secret_file"
  unset token
  echo "Stored admin token env at $secret_file." >&2
}

load_token_file() {
  if [[ -f "$secret_file" ]]; then
    local mode
    mode="$(stat -f "%Lp" "$secret_file" 2>/dev/null || stat -c "%a" "$secret_file" 2>/dev/null || true)"
    if [[ "$mode" != "600" && "$mode" != "400" ]]; then
      echo "$secret_file must be chmod 600 or 400 before loading secrets." >&2
      exit 2
    fi
    set -a
    # shellcheck disable=SC1090
    . "$secret_file"
    set +a
  fi

  if [[ -z "${FIN_OPS_HTTP_SLO_ADMIN_TOKEN:-}" && -n "${FIN_OPS_E2E_ADMIN_TOKEN:-}" ]]; then
    export FIN_OPS_HTTP_SLO_ADMIN_TOKEN="$FIN_OPS_E2E_ADMIN_TOKEN"
  fi
  if [[ -z "${FIN_OPS_E2E_ADMIN_TOKEN:-}" && -n "${FIN_OPS_HTTP_SLO_ADMIN_TOKEN:-}" ]]; then
    export FIN_OPS_E2E_ADMIN_TOKEN="$FIN_OPS_HTTP_SLO_ADMIN_TOKEN"
  fi
  if [[ -z "${FIN_OPS_HTTP_SLO_ADMIN_TOKEN:-}" || -z "${FIN_OPS_E2E_ADMIN_TOKEN:-}" ]]; then
    echo "Admin token is not configured. Run: scripts/with-production-admin-token.sh --store" >&2
    exit 2
  fi
}

if [[ "${1:-}" == "--store" ]]; then
  store_token
  exit 0
fi

if [[ $# -eq 0 || "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 2
fi

load_token_file
if [[ "${1:-}" == "--require-bearer" ]]; then
  shift
  if [[ -z "${FIN_OPS_HTTP_SLO_BEARER_TOKEN:-}" ]]; then
    echo "Dedicated production bearer token is not configured in $secret_file." >&2
    exit 2
  fi
  if [[ "$FIN_OPS_HTTP_SLO_BEARER_TOKEN" == "$FIN_OPS_HTTP_SLO_ADMIN_TOKEN" ]]; then
    echo "Dedicated production bearer token and admin token must be distinct." >&2
    exit 2
  fi
  [[ $# -gt 0 ]] || { usage; exit 2; }
fi
exec "$@"
