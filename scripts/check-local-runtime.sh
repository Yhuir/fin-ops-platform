#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_ENV_FILE="${FIN_OPS_BACKEND_ENV_FILE:-${ROOT_DIR}/.runtime/fin_ops_platform/local-postgres.env}"
MODE="${1:---all}"

case "${MODE}" in
  --all|--dependencies-only|--require-backend)
    ;;
  *)
    echo "Usage: $0 [--all|--dependencies-only|--require-backend]" >&2
    exit 2
    ;;
esac

if [[ -f "${BACKEND_ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${BACKEND_ENV_FILE}"
  set +a
fi

PYTHON_BIN="${FIN_OPS_PYTHON_BIN:-python3}"
export PYTHONPATH="${ROOT_DIR}/backend/src${PYTHONPATH:+:${PYTHONPATH}}"
export FIN_OPS_BACKEND_HOST="${FIN_OPS_BACKEND_HOST:-127.0.0.1}"
export FIN_OPS_BACKEND_PORT="${FIN_OPS_BACKEND_PORT:-8001}"
export FIN_OPS_LOCAL_RUNTIME_CHECK_MODE="${MODE}"

exec "${PYTHON_BIN}" - <<'PY'
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any


mode = os.environ.get("FIN_OPS_LOCAL_RUNTIME_CHECK_MODE", "--all")
errors: list[str] = []
warnings: list[str] = []


def ok(message: str) -> None:
    print(f"OK: {message}")


def fail(message: str) -> None:
    errors.append(message)
    print(f"ERROR: {message}", file=sys.stderr)


def warn(message: str) -> None:
    warnings.append(message)
    print(f"WARN: {message}", file=sys.stderr)


def http_json(url: str, timeout: float = 5.0) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        payload = response.read()
    return json.loads(payload.decode("utf-8"))


def http_text(url: str, timeout: float = 5.0) -> str:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


pg_url = os.environ.get("FIN_OPS_POSTGRES_DATABASE_URL") or os.environ.get("DATABASE_URL")
if not pg_url:
    fail("FIN_OPS_POSTGRES_DATABASE_URL/DATABASE_URL is not configured; local production-equivalent runtime requires PostgreSQL.")
else:
    try:
        import psycopg
        import time

        pg_topology = "ssh_tunnel" if os.environ.get("FIN_OPS_SSH_TUNNEL_HOST") else "direct"
        connect_start = time.perf_counter()
        with psycopg.connect(pg_url, connect_timeout=3) as conn:
            with conn.cursor() as cur:
                cur.execute("select 1")
                cur.fetchone()
        connect_select_ms = (time.perf_counter() - connect_start) * 1000.0

        with psycopg.connect(pg_url, connect_timeout=3) as conn:
            query_start = time.perf_counter()
            with conn.cursor() as cur:
                cur.execute(
                    """
                    select
                      (select count(*) from app.invoices),
                      (select count(*) from app.bank_transactions),
                      (select count(*) from app.import_batches),
                      (select count(*) from app.file_objects where migration_status = 'verified'),
                      (select count(*) from app.oa_applications),
                      (select count(*) from app.oa_sync_runs),
                      (select count(*) from read_model.workbench_rows),
                      (select count(*) from app.workbench_pair_relations where status = 'active')
                    """
                )
                counts = cur.fetchone()
            count_query_ms = (time.perf_counter() - query_start) * 1000.0
        ok(
            "PostgreSQL ready "
            f"(invoices={counts[0]}, bank_transactions={counts[1]}, import_batches={counts[2]}, "
            f"verified_files={counts[3]}, oa_applications={counts[4]}, oa_sync_runs={counts[5]}, "
            f"workbench_rows={counts[6]}, active_formal_relations={counts[7]}, topology={pg_topology}, "
            f"connect_select_ms={connect_select_ms:.0f}, count_query_ms={count_query_ms:.0f})"
        )
        if pg_topology == "ssh_tunnel":
            warn(
                "Local backend is using an SSH tunnel to PostgreSQL. "
                "This is valid for functional checks but is not a production performance benchmark; "
                "run p95/p99 acceptance on the server or staging where the app is co-located with PostgreSQL."
            )
        if connect_select_ms >= 100:
            warn(
                "PostgreSQL connect+select latency is high for local development "
                f"({connect_select_ms:.0f}ms). Multi-query pages such as workbench/groups will be slower locally."
            )
    except Exception as exc:  # noqa: BLE001 - startup diagnostic must surface exact dependency failure.
        fail(f"PostgreSQL check failed: {exc}")


redis_url = os.environ.get("FIN_OPS_REDIS_URL") or os.environ.get("REDIS_URL")
if redis_url:
    try:
        import redis

        client = redis.Redis.from_url(redis_url, socket_connect_timeout=1, socket_timeout=1)
        if client.ping() is not True:
            fail("Redis ping returned a non-true response.")
        else:
            ok("Redis ready")
    except Exception as exc:  # noqa: BLE001
        fail(f"Redis check failed: {exc}")
else:
    ok("Redis not configured; PostgreSQL polling remains authoritative")


object_backend = (os.environ.get("OBJECT_STORAGE_BACKEND") or "").strip().lower()
s3_endpoint = (os.environ.get("S3_ENDPOINT_URL") or "").rstrip("/")
if object_backend in {"minio", "s3"}:
    if not s3_endpoint:
        fail("OBJECT_STORAGE_BACKEND is set but S3_ENDPOINT_URL is missing.")
    else:
        try:
            http_text(f"{s3_endpoint}/minio/health/live", timeout=3)
            ok(f"Object storage ready ({object_backend})")
        except urllib.error.HTTPError as exc:
            fail(f"Object storage health failed: HTTP {exc.code}")
        except Exception as exc:  # noqa: BLE001
            fail(f"Object storage check failed: {exc}")
else:
    ok("Object storage not configured")


if mode in {"--all", "--require-backend"}:
    backend_host = os.environ.get("FIN_OPS_BACKEND_HOST", "127.0.0.1")
    backend_port = os.environ.get("FIN_OPS_BACKEND_PORT", "8001")
    base_url = f"http://{backend_host}:{backend_port}"
    try:
        health = http_json(f"{base_url}/health", timeout=5)
        storage = health.get("storage") or {}
        bootstrap = health.get("bootstrap") or {}
        repositories = bootstrap.get("repositories") or {}
        if storage.get("mode") != "postgres" or storage.get("backend") != "postgres":
            fail(f"Backend is not using PostgreSQL runtime: storage={storage}")
        elif storage.get("postgres_status") != "ready":
            fail(f"Backend PostgreSQL is not ready: {storage.get('postgres_error') or storage.get('postgres_status')}")
        elif redis_url and repositories.get("redis_status") != "ready":
            fail(f"Backend Redis is not ready: {repositories.get('redis_error') or repositories.get('redis_status')}")
        elif object_backend in {"minio", "s3"} and not repositories.get("object_storage_enabled"):
            fail("Backend object storage is not enabled.")
        else:
            ok(
                "Backend health ready "
                f"(storage={storage.get('backend')}, redis={repositories.get('redis_status')}, "
                f"object_storage={repositories.get('object_storage_backend')})"
            )
    except Exception as exc:  # noqa: BLE001
        fail(f"Backend health check failed: {exc}")

    try:
        workbench_initial = http_json(f"{base_url}/api/workbench?month=all", timeout=15)
        summary = workbench_initial.get("summary") or {}
        paired_page = workbench_initial.get("paired") or {}
        unpaired_page = workbench_initial.get("unpaired") or {}
        unpaired_groups = unpaired_page.get("groups") or []
        paired_groups = paired_page.get("groups") or []
        total_count = int(
            summary.get("totalCount")
            or summary.get("total_count")
            or (
                int(summary.get("oa_count") or 0)
                + int(summary.get("bank_count") or 0)
                + int(summary.get("invoice_count") or 0)
            )
            or 0
        )
        visible_groups = len(unpaired_groups) + len(paired_groups)
        if total_count <= 0 and visible_groups <= 0:
            fail("Workbench initial-page API returned an empty read model for month=all.")
        else:
            ok(
                "Workbench initial-page API ready "
                f"(total={total_count}, first_page_groups={visible_groups}, "
                f"unpaired_total={unpaired_page.get('total')}, paired_total={paired_page.get('total')})"
            )
    except Exception as exc:  # noqa: BLE001
        fail(
            "Workbench initial-page API check failed. "
            "Verify that scripts/start-backend.sh is running fin_ops_platform.app.main on FIN_OPS_BACKEND_PORT, "
            f"not a legacy ASGI stub: {exc}"
        )


if errors:
    print("\nLocal runtime check failed.", file=sys.stderr)
    sys.exit(1)

if warnings:
    print(f"\nLocal runtime check passed with {len(warnings)} warning(s).")
    sys.exit(0)

print("\nLocal runtime check passed.")
PY
