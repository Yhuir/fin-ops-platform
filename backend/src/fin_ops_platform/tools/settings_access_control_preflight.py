from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import statistics
import sys
import time
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

from fin_ops_platform.services.access_control_service import ASSIGNABLE_PAGE_KEYS
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings


CONTRACT = "settings-access-control-v1"
PROTECTED_ADMIN_USERNAME = "YNSYLP005"
REPRESENTATIVE_BEARER_USERNAME = "YNSYLP006"
OA_MENU_PERMISSION = "finops:app:view"
LEGACY_USER_ROLE_KEY = "finops_full_access"
LEGACY_READONLY_ROLE_KEY = "finops_read_export"
USER_ROLE_KEY = "finops_app_user"
ADMIN_ROLE_KEY = "finops_admin"
RETIRED_ADMISSION_ENVS = (
    "FIN_OPS_ALLOWED_ROLES",
    "FIN_OPS_ALLOWED_USERNAMES",
    "FIN_OPS_READONLY_EXPORT_USERNAMES",
    "FIN_OPS_" + "ADMIN_USERNAMES",
)


def _postgres_settings() -> PostgresSettings:
    settings = PostgresSettings.from_env()
    migrator_url = (os.getenv("FIN_OPS_POSTGRES_MIGRATOR_DATABASE_URL") or "").strip()
    return replace(settings, database_url=migrator_url) if migrator_url else settings


def _strings(value: object) -> list[str]:
    return sorted({str(item or "").strip() for item in list(value or []) if str(item or "").strip()})


def _hash(value: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}\0{value}".encode()).hexdigest()


def _canonical_accounts(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    page_accounts = payload.get("page_access_accounts")
    if isinstance(page_accounts, list):
        accounts = [
            {
                "username": str(account.get("username") or "").strip(),
                "page_keys": _strings(account.get("page_keys")),
            }
            for account in page_accounts
            if isinstance(account, dict) and str(account.get("username") or "").strip()
        ]
        return sorted(accounts, key=lambda account: account["username"].casefold()), "page_access"

    accounts = [
        {"username": username, "page_keys": sorted(ASSIGNABLE_PAGE_KEYS)}
        for username in _strings(payload.get("full_access_usernames"))
        if username != PROTECTED_ADMIN_USERNAME
    ]
    return accounts, "legacy"


def _session_fact(payload: dict[str, Any], salt: str) -> dict[str, Any]:
    user = payload.get("user") if isinstance(payload.get("user"), dict) else {}
    username = str(user.get("username") or "").strip()
    allowed_page_keys = _strings(payload.get("allowed_page_keys"))
    legacy_tier = str(payload.get("access_tier") or "")
    return {
        "username_sha256": _hash(username, salt) if username else "",
        "identity_present": bool(username),
        "is_protected_administrator": username == PROTECTED_ADMIN_USERNAME,
        "is_representative_bearer": username == REPRESENTATIVE_BEARER_USERNAME,
        "can_access_app": payload.get("can_access_app") is True or legacy_tier in {"full_access", "read_export_only", "admin"},
        "can_admin_access": payload.get("can_admin_access") is True or legacy_tier == "admin",
        "allowed_page_count": len(allowed_page_keys),
        "http_status": int(payload.get("_preflight_http_status") or 0),
        "credential_source": str(payload.get("_preflight_credential_source") or ""),
    }


def build_report(
    *,
    release: str,
    database: dict[str, Any],
    environment: dict[str, Any],
    oa_roles: dict[str, Any],
    admin_session: dict[str, Any],
    bearer_session: dict[str, Any],
    deployment: dict[str, Any] | None = None,
) -> dict[str, Any]:
    salt = hashlib.sha256(f"{CONTRACT}\0{release}".encode()).hexdigest()
    payload = database.get("settings_payload") if isinstance(database.get("settings_payload"), dict) else {}
    accounts, database_state = _canonical_accounts(payload)
    usernames = [str(account["username"]) for account in accounts]
    admin = _session_fact(admin_session, salt)
    bearer = _session_fact(bearer_session, salt)
    retired_env = sorted(
        name for name, present in dict(environment.get("retired_admission_env_present") or {}).items() if present
    )

    expected_members = sorted(usernames)
    topology = str(oa_roles.get("topology") or "invalid")
    actual_user_members = _strings(oa_roles.get("user_members"))
    actual_admin_members = _strings(oa_roles.get("admin_members"))
    if topology == "legacy":
        member_match = actual_user_members == expected_members and actual_admin_members == [PROTECTED_ADMIN_USERNAME]
    elif topology == "page_access":
        member_match = actual_user_members == expected_members and actual_admin_members == [PROTECTED_ADMIN_USERNAME]
    else:
        member_match = False

    blockers: list[str] = []
    if database_state == "page_access":
        if not all((database.get("migration_0165_applied"), database.get("constraint_present"), database.get("constraint_validated"))):
            blockers.append("database_guard_incomplete")
    elif database_state != "legacy":
        blockers.append("database_payload_invalid")
    if topology not in {"legacy", "page_access"}:
        blockers.append("oa_topology_invalid")
    if not member_match:
        blockers.append("oa_membership_mismatch")
    if retired_env:
        blockers.append("retired_admission_environment_present")
    if not (
        admin["http_status"] == 200
        and admin["credential_source"] == "admin_stdin"
        and admin["is_protected_administrator"]
        and admin["can_admin_access"]
    ):
        blockers.append("admin_session_invalid")
    bearer_expected_access = REPRESENTATIVE_BEARER_USERNAME in usernames
    if not (
        bearer["http_status"] == 200
        and bearer["credential_source"] == "dedicated_bearer_stdin"
        and bearer["is_representative_bearer"]
        and not bearer["can_admin_access"]
        and bearer["can_access_app"] is bearer_expected_access
    ):
        blockers.append("bearer_session_invalid")

    eligible = not blockers
    return {
        "contract": CONTRACT,
        "release": release,
        "eligible": eligible,
        "cutover_eligible": eligible,
        "state": "steady" if database_state == "page_access" and topology == "page_access" else "cutover",
        "blockers": blockers,
        "protected_administrator": PROTECTED_ADMIN_USERNAME,
        "database": {
            "state": database_state,
            "migration_0165_applied": bool(database.get("migration_0165_applied")),
            "constraint_present": bool(database.get("constraint_present")),
            "constraint_validated": bool(database.get("constraint_validated")),
            "account_count": len(accounts),
            "account_hashes": [_hash(username, salt) for username in sorted(usernames)],
        },
        "oa": {
            "topology": topology,
            "matches_target": member_match,
            "migration_required": topology == "legacy",
            "user_member_count": len(actual_user_members),
            "admin_member_count": len(actual_admin_members),
            "user_member_hashes": [_hash(username, salt) for username in actual_user_members],
        },
        "sessions": {"admin": admin, "bearer": bearer},
        "environment": {"retired_admission_env_present": retired_env},
        "deployment": dict(deployment or {}),
    }


def collect_database_facts(connection: Any) -> dict[str, Any]:
    row = connection.fetch_one(
        "select settings_payload from app.app_settings where settings_key = %s",
        ("app_settings",),
    )
    migration = connection.fetch_one(
        "select exists(select 1 from public.schema_migrations where version = %s) as applied",
        ("0165",),
    )
    constraint = connection.fetch_one(
        """
        select true as present, convalidated
        from pg_constraint
        where conrelid = 'app.app_settings'::regclass
          and conname = %s
        """,
        ("app_settings_page_access_accounts_guard",),
    )
    return {
        "settings_payload": dict((row or {}).get("settings_payload") or {}),
        "migration_0165_applied": bool((migration or {}).get("applied")),
        "constraint_present": constraint is not None,
        "constraint_validated": bool((constraint or {}).get("convalidated")),
    }


def _oa_connect(*, autocommit: bool):
    import pymysql  # type: ignore

    return pymysql.connect(
        host=os.environ["FIN_OPS_OA_ROLE_SYNC_HOST"],
        port=int(os.getenv("FIN_OPS_OA_ROLE_SYNC_PORT", "3306")),
        user=os.environ["FIN_OPS_OA_ROLE_SYNC_USERNAME"],
        password=os.environ["FIN_OPS_OA_ROLE_SYNC_PASSWORD"],
        database=os.environ["FIN_OPS_OA_ROLE_SYNC_DATABASE"],
        charset="utf8mb4",
        autocommit=autocommit,
        connect_timeout=int(os.getenv("FIN_OPS_OA_ROLE_SYNC_CONNECT_TIMEOUT_SECONDS", "5")),
        read_timeout=int(os.getenv("FIN_OPS_OA_ROLE_SYNC_READ_TIMEOUT_SECONDS", "10")),
        write_timeout=int(os.getenv("FIN_OPS_OA_ROLE_SYNC_WRITE_TIMEOUT_SECONDS", "10")),
    )


def collect_oa_role_facts() -> dict[str, Any]:
    enabled = str(os.getenv("FIN_OPS_OA_ROLE_SYNC_ENABLED", "")).strip().lower() in {"1", "true", "yes", "on"}
    if not enabled or os.getenv("FIN_OPS_OA_REQUIRED_PERMISSION", "").strip() != OA_MENU_PERMISSION:
        return {"topology": "invalid", "user_members": [], "admin_members": []}
    connection = _oa_connect(autocommit=True)
    try:
        with connection.cursor() as cursor:
            cursor.execute("select menu_id from sys_menu where perms = %s order by menu_id", (OA_MENU_PERMISSION,))
            menu_rows = list(cursor.fetchall() or [])
            cursor.execute(
                "select role_id, role_key from sys_role where role_key in (%s, %s, %s, %s) order by role_key, role_id",
                (LEGACY_READONLY_ROLE_KEY, LEGACY_USER_ROLE_KEY, USER_ROLE_KEY, ADMIN_ROLE_KEY),
            )
            role_rows = list(cursor.fetchall() or [])
            cursor.execute(
                """
                select r.role_key
                from sys_role_menu rm
                join sys_role r on r.role_id = rm.role_id
                join sys_menu m on m.menu_id = rm.menu_id
                where m.perms = %s
                order by r.role_key
                """,
                (OA_MENU_PERMISSION,),
            )
            binding_keys = [str(row[0]) for row in list(cursor.fetchall() or [])]
            cursor.execute(
                """
                select u.user_name, r.role_key
                from sys_user_role ur
                join sys_user u on u.user_id = ur.user_id
                join sys_role r on r.role_id = ur.role_id
                where r.role_key in (%s, %s, %s, %s)
                order by r.role_key, u.user_name
                """,
                (LEGACY_READONLY_ROLE_KEY, LEGACY_USER_ROLE_KEY, USER_ROLE_KEY, ADMIN_ROLE_KEY),
            )
            member_rows = list(cursor.fetchall() or [])
    finally:
        connection.close()

    counts = {key: sum(1 for _role_id, role_key in role_rows if str(role_key) == key) for key in (
        LEGACY_READONLY_ROLE_KEY, LEGACY_USER_ROLE_KEY, USER_ROLE_KEY, ADMIN_ROLE_KEY
    )}
    if len(menu_rows) != 1 or counts[ADMIN_ROLE_KEY] != 1:
        topology = "invalid"
        user_key = USER_ROLE_KEY
    elif counts[USER_ROLE_KEY] == 1 and counts[LEGACY_USER_ROLE_KEY] == 0 and sorted(binding_keys) == sorted([USER_ROLE_KEY, ADMIN_ROLE_KEY]):
        topology = "page_access"
        user_key = USER_ROLE_KEY
    elif counts[LEGACY_USER_ROLE_KEY] == 1 and counts[USER_ROLE_KEY] == 0 and counts[LEGACY_READONLY_ROLE_KEY] == 1 and sorted(binding_keys) == sorted([LEGACY_READONLY_ROLE_KEY, LEGACY_USER_ROLE_KEY, ADMIN_ROLE_KEY]):
        topology = "legacy"
        user_key = LEGACY_USER_ROLE_KEY
    else:
        topology = "invalid"
        user_key = USER_ROLE_KEY
    return {
        "topology": topology,
        "user_members": [str(username) for username, role_key in member_rows if str(role_key) == user_key],
        "admin_members": [str(username) for username, role_key in member_rows if str(role_key) == ADMIN_ROLE_KEY],
    }


def migrate_oa_role_topology() -> str:
    """Transactionally replace the exact legacy three-role menu projection with two roles."""
    connection = _oa_connect(autocommit=False)
    try:
        with connection.cursor() as cursor:
            cursor.execute("select menu_id from sys_menu where perms = %s for update", (OA_MENU_PERMISSION,))
            menu_rows = list(cursor.fetchall() or [])
            cursor.execute(
                "select role_id, role_key from sys_role where role_key in (%s, %s, %s, %s) for update",
                (LEGACY_READONLY_ROLE_KEY, LEGACY_USER_ROLE_KEY, USER_ROLE_KEY, ADMIN_ROLE_KEY),
            )
            role_rows = list(cursor.fetchall() or [])
            if len(menu_rows) != 1:
                raise RuntimeError("OA fin-ops menu permission must resolve exactly once.")
            menu_id = int(menu_rows[0][0])
            role_ids: dict[str, list[int]] = {}
            for role_id, role_key in role_rows:
                role_ids.setdefault(str(role_key), []).append(int(role_id))
            cursor.execute(
                "select role_id from sys_role_menu where menu_id = %s for update",
                (menu_id,),
            )
            actual_bindings = [int(row[0]) for row in list(cursor.fetchall() or [])]

            page_ids = role_ids.get(USER_ROLE_KEY, [])
            admin_ids = role_ids.get(ADMIN_ROLE_KEY, [])
            legacy_user_ids = role_ids.get(LEGACY_USER_ROLE_KEY, [])
            legacy_read_ids = role_ids.get(LEGACY_READONLY_ROLE_KEY, [])
            if len(page_ids) == 1 and not legacy_user_ids and len(admin_ids) == 1:
                if sorted(actual_bindings) != sorted([page_ids[0], admin_ids[0]]):
                    raise RuntimeError("OA page-access menu bindings drifted.")
                connection.commit()
                return "already_migrated"
            if not (len(legacy_user_ids) == len(legacy_read_ids) == len(admin_ids) == 1 and not page_ids):
                raise RuntimeError("OA legacy role topology is not the exact migratable state.")
            if sorted(actual_bindings) != sorted([legacy_user_ids[0], legacy_read_ids[0], admin_ids[0]]):
                raise RuntimeError("OA legacy menu bindings are not the exact migratable state.")

            cursor.execute(
                "update sys_role set role_key = %s where role_id = %s and role_key = %s",
                (USER_ROLE_KEY, legacy_user_ids[0], LEGACY_USER_ROLE_KEY),
            )
            cursor.execute(
                "delete from sys_role_menu where role_id = %s and menu_id = %s",
                (legacy_read_ids[0], menu_id),
            )
            cursor.execute("delete from sys_user_role where role_id = %s", (legacy_read_ids[0],))
            connection.commit()
            return "migrated"
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _load_json(path: str) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _http_request(*, base_url: str, method: str, path: str, token: str) -> dict[str, Any]:
    request = urllib_request.Request(
        f"{base_url.rstrip('/')}{path}",
        method=method,
        headers={"Authorization": f"Bearer {token}"},
    )
    started = time.perf_counter()
    try:
        response = urllib_request.urlopen(request, timeout=20)
        status = int(response.status)
        raw = response.read()
    except urllib_error.HTTPError as exc:
        status = int(exc.code)
        raw = exc.read()
    elapsed_ms = (time.perf_counter() - started) * 1000
    try:
        payload = json.loads(raw.decode()) if raw else {}
    except (UnicodeDecodeError, ValueError):
        payload = {}
    return {"status": status, "payload": payload if isinstance(payload, dict) else {}, "elapsed_ms": elapsed_ms}


def _latency_summary(values: list[float]) -> dict[str, float | int]:
    ordered = sorted(values)
    p95_index = max(0, min(len(ordered) - 1, int(len(ordered) * 0.95 + 0.999) - 1))
    return {
        "samples": len(ordered),
        "p50_ms": round(statistics.median(ordered), 3),
        "p95_ms": round(ordered[p95_index], 3),
        "max_ms": round(max(ordered), 3),
    }


def run_post_deploy(
    *,
    release: str,
    base_url: str,
    preflight_path: str,
    output_path: str,
    admin_token: str,
    bearer_token: str,
    oa_base_url: str,
) -> tuple[dict[str, Any], int]:
    del oa_base_url
    preflight = _load_json(preflight_path)
    report: dict[str, Any] = {
        "contract": CONTRACT,
        "release": release,
        "status": "fail",
        "preflight_sha256": hashlib.sha256(Path(preflight_path).read_bytes()).hexdigest(),
        "checks": {},
    }
    try:
        if preflight.get("release") != release or preflight.get("eligible") is not True:
            raise RuntimeError("approved preflight does not match this eligible release")
        report["checks"]["oa_topology_migration"] = migrate_oa_role_topology()

        database = collect_database_facts(PostgresConnection(_postgres_settings()))
        if not all((database["migration_0165_applied"], database["constraint_present"], database["constraint_validated"])):
            raise RuntimeError("page-access database guard is incomplete")
        oa = collect_oa_role_facts()
        accounts, state = _canonical_accounts(database["settings_payload"])
        if state != "page_access" or oa.get("topology") != "page_access":
            raise RuntimeError("page-access production state is not steady")
        if _strings(oa.get("user_members")) != sorted(str(account["username"]) for account in accounts):
            raise RuntimeError("OA user-role membership does not match page-access accounts")
        if _strings(oa.get("admin_members")) != [PROTECTED_ADMIN_USERNAME]:
            raise RuntimeError("OA admin-role membership drifted")

        latencies: list[float] = []
        admin_session: dict[str, Any] = {}
        for _ in range(8):
            response = _http_request(base_url=base_url, method="GET", path="/api/session/me", token=admin_token)
            if response["status"] != 200:
                raise RuntimeError("admin session verification failed")
            admin_session = response["payload"]
            latencies.append(float(response["elapsed_ms"]))
        if admin_session.get("can_admin_access") is not True or admin_session.get("user", {}).get("username") != PROTECTED_ADMIN_USERNAME:
            raise RuntimeError("005 is not the sole effective administrator")
        acl = _http_request(base_url=base_url, method="GET", path="/api/workbench/settings/access-control", token=admin_token)
        if acl["status"] != 200 or acl["payload"].get("version") is None:
            raise RuntimeError("access-control read contract failed")
        search = _http_request(base_url=base_url, method="GET", path="/api/workbench/settings/access-control/users?q=005&limit=5", token=admin_token)
        if search["status"] != 200 or not isinstance(search["payload"].get("users"), list):
            raise RuntimeError("OA user directory search contract failed")
        bearer_admin = _http_request(base_url=base_url, method="GET", path="/api/workbench/settings/access-control", token=bearer_token)
        if bearer_admin["status"] != 403:
            raise RuntimeError("non-admin bearer reached access-control plane")

        latency = _latency_summary(latencies)
        if float(latency["p95_ms"]) > 1000:
            raise RuntimeError("session p95 exceeds 1000ms")
        report["checks"].update({
            "database_guard": "pass",
            "oa_topology": "pass",
            "admin_control_plane": "pass",
            "bearer_admin_denial": "pass",
            "oa_user_directory": "pass",
            "session_latency": latency,
        })
        report["status"] = "pass"
    except Exception as exc:
        report["error"] = str(exc)

    output = Path(output_path)
    serialized = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(serialized, encoding="utf-8")
    temporary.replace(output)
    output.chmod(0o600)
    return report, 0 if report["status"] == "pass" else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Settings page-access production preflight.")
    parser.add_argument("--release", required=True)
    parser.add_argument("--admin-session-json")
    parser.add_argument("--bearer-session-json")
    parser.add_argument("--deployment-facts-json")
    parser.add_argument("--post-deploy", action="store_true")
    parser.add_argument("--database-guard-only", action="store_true")
    parser.add_argument("--preflight-artifact")
    parser.add_argument("--base-url", default="http://127.0.0.1:18001")
    parser.add_argument("--oa-base-url", default=(os.getenv("FIN_OPS_OA_BASE_URL") or "").strip())
    parser.add_argument("--output")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if args.database_guard_only:
        database = collect_database_facts(PostgresConnection(_postgres_settings()))
        passed = all((database["migration_0165_applied"], database["constraint_present"], database["constraint_validated"]))
        report = {
            "contract": CONTRACT,
            "release": args.release,
            "status": "pass" if passed else "fail",
            "database": {
                "migration_0165_applied": database["migration_0165_applied"],
                "constraint_present": database["constraint_present"],
                "constraint_validated": database["constraint_validated"],
            },
        }
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if passed else 2

    if args.post_deploy:
        if not args.preflight_artifact or not args.output:
            parser.error("--post-deploy requires --preflight-artifact and --output")
        admin_token = sys.stdin.readline().rstrip("\r\n")
        bearer_token = sys.stdin.readline().rstrip("\r\n")
        report, status = run_post_deploy(
            release=args.release,
            base_url=args.base_url,
            preflight_path=args.preflight_artifact,
            output_path=args.output,
            admin_token=admin_token,
            bearer_token=bearer_token,
            oa_base_url=args.oa_base_url,
        )
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return status

    if not args.admin_session_json or not args.bearer_session_json:
        parser.error("preflight requires --admin-session-json and --bearer-session-json")
    report = build_report(
        release=args.release,
        database=collect_database_facts(PostgresConnection(_postgres_settings())),
        environment={"retired_admission_env_present": {name: name in os.environ for name in RETIRED_ADMISSION_ENVS}},
        oa_roles=collect_oa_role_facts(),
        admin_session=_load_json(args.admin_session_json),
        bearer_session=_load_json(args.bearer_session_json),
        deployment=_load_json(args.deployment_facts_json) if args.deployment_facts_json else {},
    )
    serialized = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        output = Path(args.output)
        temporary = output.with_suffix(output.suffix + ".tmp")
        temporary.write_text(serialized, encoding="utf-8")
        temporary.replace(output)
        output.chmod(0o600)
    if args.json:
        print(serialized, end="")
    return 0 if report["eligible"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
