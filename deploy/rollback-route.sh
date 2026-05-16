#!/usr/bin/env bash
set -euo pipefail

CHANGE_ID=""
ROUTE_GROUP=""
TARGET_BACKEND=""
DRY_RUN=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --change)
      CHANGE_ID="${2:-}"
      shift 2
      ;;
    --route-group)
      ROUTE_GROUP="${2:-}"
      shift 2
      ;;
    --target)
      TARGET_BACKEND="${2:-}"
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

if [[ -z "$CHANGE_ID" || -z "$ROUTE_GROUP" || -z "$TARGET_BACKEND" ]]; then
  echo "usage: $0 --change CHANGE_ID --route-group GROUP --target python|axum [--dry-run|--execute]" >&2
  exit 64
fi

if [[ "$TARGET_BACKEND" != "python" && "$TARGET_BACKEND" != "axum" ]]; then
  echo "target must be python or axum" >&2
  exit 64
fi

if [[ ! "$CHANGE_ID" =~ ^[A-Za-z0-9._:-]+$ ]]; then
  echo "change id contains unsupported characters" >&2
  exit 64
fi

if [[ ! "$ROUTE_GROUP" =~ ^[A-Za-z0-9._:-]+$ ]]; then
  echo "route group contains unsupported characters" >&2
  exit 64
fi

if [[ "$DRY_RUN" -eq 0 && "${FIN_OPS_CUTOVER_EXECUTE:-0}" != "1" ]]; then
  echo "refusing route change: set FIN_OPS_CUTOVER_EXECUTE=1 only after approved P4-11 authorization" >&2
  exit 78
fi

printf '{"action":"rollback-route","dry_run":%s,"change_id":"%s","route_group":"%s","target_backend":"%s"}\n' \
  "$([[ "$DRY_RUN" -eq 1 ]] && echo true || echo false)" \
  "$CHANGE_ID" \
  "$ROUTE_GROUP" \
  "$TARGET_BACKEND"
