#!/usr/bin/env bash
set -euo pipefail

CHANGE_ID=""
FLAG=""
VALUE=""
DRY_RUN=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --change)
      CHANGE_ID="${2:-}"
      shift 2
      ;;
    --flag)
      FLAG="${2:-}"
      shift 2
      ;;
    --value)
      VALUE="${2:-}"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --execute)
      DRY_RUN=0
      shift
      ;;
    *)
      echo "unknown argument: $1" >&2
      exit 64
      ;;
  esac
done

if [[ -z "$CHANGE_ID" || -z "$FLAG" || -z "$VALUE" ]]; then
  echo "usage: $0 --change CHANGE_ID --flag FLAG --value VALUE [--dry-run|--execute]" >&2
  exit 64
fi

if [[ ! "$CHANGE_ID" =~ ^[A-Za-z0-9._:-]+$ ]]; then
  echo "change id contains unsupported characters" >&2
  exit 64
fi

case "$FLAG" in
  backend.shadow_read.enabled|backend.dual_write.enabled|backend.axum_read.enabled|backend.legacy_write.enabled)
    ;;
  *)
    echo "flag is not in the approved backend-refactor allowlist" >&2
    exit 64
    ;;
esac

case "$VALUE" in
  true|false)
    ;;
  *)
    echo "value must be true or false" >&2
    exit 64
    ;;
esac

if [[ "$DRY_RUN" -eq 0 && "${FIN_OPS_CUTOVER_EXECUTE:-0}" != "1" ]]; then
  echo "refusing feature flag change: set FIN_OPS_CUTOVER_EXECUTE=1 only after approved P4-11 authorization" >&2
  exit 78
fi

printf '{"action":"set-feature-flag","dry_run":%s,"change_id":"%s","flag":"%s","value":"%s"}\n' \
  "$([[ "$DRY_RUN" -eq 1 ]] && echo true || echo false)" \
  "$CHANGE_ID" \
  "$FLAG" \
  "$VALUE"
