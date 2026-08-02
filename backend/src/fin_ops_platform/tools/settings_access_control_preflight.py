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

from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings


PROTECTED_ADMIN_USERNAME = "YNSYLP005"
REPRESENTATIVE_BEARER_USERNAME = "YNSYLP006"
ROLE_TIERS = ("read_export_only", "full_access", "admin")
OA_MENU_PERMISSION = "finops:app:view"
OA_MENU_NAME = "财务运营平台"
ROLE_KEYS = {
    "read_export_only": "finops_read_export",
    "full_access": "finops_full_access",
    "admin": "finops_admin",
}
RETIRED_ADMISSION_ENVS = (
    "FIN_OPS_ALLOWED_ROLES",
    "FIN_OPS_ALLOWED_USERNAMES",
    "FIN_OPS_READONLY_EXPORT_USERNAMES",
)
LEGACY_ADMIN_ENV = "FIN_OPS_" + "ADMIN_USERNAMES"


def _postgres_settings() -> PostgresSettings:
    settings = PostgresSettings.from_env()
    migrator_url = (os.getenv("FIN_OPS_POSTGRES_MIGRATOR_DATABASE_URL") or "").strip()
    return replace(settings, database_url=migrator_url) if migrator_url else settings


def _strings(value: object) -> list[str]:
    return sorted({str(item).strip() for item in list(value or []) if str(item).strip()})


def _hash_username(username: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}\0{username}".encode("utf-8")).hexdigest()


def _hashed_usernames(usernames: list[str], salt: str) -> list[str]:
    return [_hash_username(username, salt) for username in sorted(usernames)]


def _ids(value: object) -> list[int]:
    return sorted({int(item) for item in list(value or [])})


def _hash_oa_id(kind: str, value: int, salt: str) -> str:
    return hashlib.sha256(f"{salt}\0{kind}\0{value}".encode("utf-8")).hexdigest()


def _hash_menu_binding(role_id: int, menu_id: int, salt: str) -> str:
    return hashlib.sha256(
        f"{salt}\0role_menu\0{role_id}\0{menu_id}".encode("utf-8")
    ).hexdigest()


def _hash_fingerprint_set(values: list[str]) -> str:
    return hashlib.sha256("\n".join(sorted(values)).encode("ascii")).hexdigest()


def _session_fact(payload: dict[str, Any], salt: str) -> dict[str, Any]:
    user = payload.get("user") if isinstance(payload.get("user"), dict) else {}
    username = str(user.get("username") or "").strip()
    return {
        "username_sha256": _hash_username(username, salt) if username else "",
        "access_tier": str(payload.get("access_tier") or "denied"),
        "can_admin_access": payload.get("can_admin_access") is True,
        "identity_present": bool(username),
        "is_protected_administrator": username == PROTECTED_ADMIN_USERNAME,
        "is_representative_bearer": username == REPRESENTATIVE_BEARER_USERNAME,
        "oa_menu_permission_present": OA_MENU_PERMISSION in _strings(payload.get("permissions")),
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
    salt = hashlib.sha256(f"settings-access-control-v1\0{release}".encode("utf-8")).hexdigest()
    payload = database.get("settings_payload") if isinstance(database.get("settings_payload"), dict) else {}
    current = {
        "allowed": _strings(payload.get("allowed_usernames")),
        "readonly": _strings(payload.get("readonly_export_usernames")),
        "full_access": _strings(payload.get("full_access_usernames")),
        "admin": _strings(payload.get("admin_usernames")),
    }
    target = {
        "allowed": sorted(set(current["allowed"]) | {PROTECTED_ADMIN_USERNAME}),
        "readonly": [item for item in current["readonly"] if item != PROTECTED_ADMIN_USERNAME],
        "full_access": [item for item in current["full_access"] if item != PROTECTED_ADMIN_USERNAME],
        "admin": [PROTECTED_ADMIN_USERNAME],
    }
    admin = _session_fact(admin_session, salt)
    bearer = _session_fact(bearer_session, salt)
    oa_members = {
        tier: _strings((oa_roles.get("members") or {}).get(tier))
        for tier in ROLE_TIERS
    }
    target_oa = {
        "read_export_only": target["readonly"],
        "full_access": target["full_access"],
        "admin": target["admin"],
    }
    oa_enabled = oa_roles.get("enabled") is True
    oa_configured = oa_roles.get("configured") is not False
    selector = str(oa_roles.get("required_permission") or "")
    selector_exact = selector == OA_MENU_PERMISSION
    role_keys_exact = oa_roles.get("role_keys_exact") is not False
    menu_ids = _ids(oa_roles.get("menu_ids"))
    menu_unique = len(menu_ids) == 1
    role_ids = {
        tier: _ids((oa_roles.get("role_ids") or {}).get(tier))
        for tier in ROLE_TIERS
    }
    roles_unique = all(len(values) == 1 for values in role_ids.values())
    roles_distinct = roles_unique and len({values[0] for values in role_ids.values()}) == len(ROLE_TIERS)
    bindings = {
        (int(item["role_id"]), int(item["menu_id"]))
        for item in list(oa_roles.get("bindings") or [])
        if isinstance(item, dict) and item.get("role_id") is not None and item.get("menu_id") is not None
    }
    expected_bindings = (
        {(role_ids[tier][0], menu_ids[0]) for tier in ROLE_TIERS}
        if menu_unique and roles_distinct
        else set()
    )
    dedicated_bindings_exact = bool(expected_bindings) and expected_bindings.issubset(bindings)
    non_dedicated_bindings = sorted(bindings - expected_bindings) if dedicated_bindings_exact else []
    binding_hashes = [
        _hash_menu_binding(role_id, menu_id, salt)
        for role_id, menu_id in sorted(bindings)
    ]
    expected_binding_hashes = [
        _hash_menu_binding(role_id, menu_id, salt)
        for role_id, menu_id in sorted(expected_bindings)
    ]
    cleanup_target_hashes = [
        _hash_menu_binding(role_id, menu_id, salt)
        for role_id, menu_id in non_dedicated_bindings
    ]
    oa_matches_target = oa_enabled and oa_members == target_oa
    legacy_environment_admins = _strings(environment.get("admin_usernames"))
    retired_environment = sorted(
        name
        for name, present in dict(environment.get("retired_admission_env_present") or {}).items()
        if name in RETIRED_ADMISSION_ENVS and present is True
    )
    identities_distinct = bool(admin["username_sha256"] and bearer["username_sha256"])
    identities_distinct = identities_distinct and admin["username_sha256"] != bearer["username_sha256"]
    base_eligible = all(
        (
            admin["identity_present"],
            admin["is_protected_administrator"],
            admin["access_tier"] == "admin",
            admin["can_admin_access"],
            admin["http_status"] == 200,
            admin["credential_source"] == "admin_stdin",
            bearer["identity_present"],
            not bearer["is_protected_administrator"],
            bearer["is_representative_bearer"],
            bearer["oa_menu_permission_present"],
            bearer["access_tier"] == "denied",
            not bearer["can_admin_access"],
            bearer["http_status"] == 200,
            bearer["credential_source"] == "dedicated_bearer_stdin",
            identities_distinct,
            oa_enabled,
            oa_configured,
            selector_exact,
            role_keys_exact,
            menu_unique,
            roles_distinct,
            dedicated_bindings_exact,
            oa_matches_target,
            not legacy_environment_admins,
            not retired_environment,
        )
    )
    cleanup_eligible = base_eligible and bool(non_dedicated_bindings)
    eligible = base_eligible and not non_dedicated_bindings
    before_hash = hashlib.sha256(json.dumps(current, sort_keys=True).encode("utf-8")).hexdigest()
    after_hash = hashlib.sha256(json.dumps(target, sort_keys=True).encode("utf-8")).hexdigest()
    return {
        "contract": "settings-access-control-v1",
        "release": release,
        "eligible": eligible,
        "protected_administrator": PROTECTED_ADMIN_USERNAME,
        "database": {
            "migration_0132_applied": database.get("migration_0132_applied") is True,
            "constraint_present": database.get("constraint_present") is True,
            "constraint_validated": database.get("constraint_validated") is True,
            "access_control_version": int(payload.get("access_control_version") or 0),
            "member_counts": {key: len(value) for key, value in current.items()},
            "member_hashes": {key: _hashed_usernames(value, salt) for key, value in current.items()},
        },
        "environment": {
            "admin_is_runtime_configurable": False,
            "legacy_admin_member_count": len(legacy_environment_admins),
            "legacy_admin_member_hashes": _hashed_usernames(legacy_environment_admins, salt),
            "retired_admission_env_present": retired_environment,
        },
        "oa": {
            "enabled": oa_enabled,
            "configured": oa_configured,
            "selector_exact": selector_exact,
            "selector_sha256": hashlib.sha256(selector.encode("utf-8")).hexdigest() if selector else "",
            "role_keys_exact": role_keys_exact,
            "menu_count": len(menu_ids),
            "menu_id_hashes": [_hash_oa_id("menu", item, salt) for item in menu_ids],
            "role_counts": {tier: len(values) for tier, values in role_ids.items()},
            "role_id_hashes": {
                tier: [_hash_oa_id("role", item, salt) for item in values]
                for tier, values in role_ids.items()
            },
            "matches_target": oa_matches_target,
            "member_counts": {key: len(value) for key, value in oa_members.items()},
            "member_hashes": {key: _hashed_usernames(value, salt) for key, value in oa_members.items()},
            "dedicated_bindings_exact": dedicated_bindings_exact,
            "cleanup_eligible": cleanup_eligible,
            "menu_binding_cleanup": {
                "required": bool(non_dedicated_bindings),
                "current_count": len(bindings),
                "dedicated_count": len(expected_bindings & bindings),
                "target_count": len(cleanup_target_hashes),
                "target_hashes": cleanup_target_hashes,
                "rollback_target_hashes": cleanup_target_hashes,
                "target_set_sha256": _hash_fingerprint_set(cleanup_target_hashes),
                "before_sha256": _hash_fingerprint_set(binding_hashes),
                "after_sha256": _hash_fingerprint_set(expected_binding_hashes),
            },
        },
        "sessions": {
            "admin": admin,
            "bearer": bearer,
            "identities_distinct": identities_distinct,
        },
        "dry_run_cleanup": {
            "required": current != target,
            "before_sha256": before_hash,
            "after_sha256": after_hash,
            "target_member_counts": {key: len(value) for key, value in target.items()},
            "removed_admin_count": len(set(current["admin"]) - {PROTECTED_ADMIN_USERNAME}),
        },
        "deployment": dict(deployment or {}),
    }


def collect_database_facts(connection: Any) -> dict[str, Any]:
    row = connection.fetch_one(
        "select settings_payload from app.app_settings where settings_key = %s",
        ("app_settings",),
    )
    migration = connection.fetch_one(
        "select exists(select 1 from public.schema_migrations where version = %s) as applied",
        ("0132",),
    )
    constraint = connection.fetch_one(
        """
        select true as present, convalidated
        from pg_constraint
        where conrelid = 'app.app_settings'::regclass
          and conname = %s
        """,
        ("app_settings_access_control_guard",),
    )
    return {
        "settings_payload": dict((row or {}).get("settings_payload") or {}),
        "migration_0132_applied": bool((migration or {}).get("applied")),
        "constraint_present": constraint is not None,
        "constraint_validated": bool((constraint or {}).get("convalidated")),
    }


def collect_oa_role_facts() -> dict[str, Any]:
    enabled = str(os.getenv("FIN_OPS_OA_ROLE_SYNC_ENABLED", "")).strip().lower() in {"1", "true", "yes", "on"}
    required_permission = os.getenv("FIN_OPS_OA_REQUIRED_PERMISSION", "").strip()
    role_keys_exact = all(
        (os.getenv(env_name, expected).strip() or expected) == expected
        for env_name, expected in (
            ("FIN_OPS_OA_ROLE_SYNC_READONLY_ROLE_KEY", ROLE_KEYS["read_export_only"]),
            ("FIN_OPS_OA_ROLE_SYNC_FULL_ACCESS_ROLE_KEY", ROLE_KEYS["full_access"]),
            ("FIN_OPS_OA_ROLE_SYNC_ADMIN_ROLE_KEY", ROLE_KEYS["admin"]),
        )
    )
    empty = {
        "enabled": enabled,
        "configured": False,
        "required_permission": required_permission,
        "role_keys_exact": role_keys_exact,
        "menu_ids": [],
        "role_ids": {tier: [] for tier in ROLE_TIERS},
        "bindings": [],
        "members": {tier: [] for tier in ROLE_TIERS},
    }
    if not enabled:
        return empty
    required_connection = (
        "FIN_OPS_OA_ROLE_SYNC_HOST",
        "FIN_OPS_OA_ROLE_SYNC_DATABASE",
        "FIN_OPS_OA_ROLE_SYNC_USERNAME",
        "FIN_OPS_OA_ROLE_SYNC_PASSWORD",
    )
    if required_permission != OA_MENU_PERMISSION or not role_keys_exact or any(
        not os.getenv(name, "").strip() for name in required_connection
    ):
        return empty
    import pymysql  # type: ignore

    connection = pymysql.connect(
        host=os.environ["FIN_OPS_OA_ROLE_SYNC_HOST"],
        port=int(os.getenv("FIN_OPS_OA_ROLE_SYNC_PORT", "3306")),
        user=os.environ["FIN_OPS_OA_ROLE_SYNC_USERNAME"],
        password=os.environ["FIN_OPS_OA_ROLE_SYNC_PASSWORD"],
        database=os.environ["FIN_OPS_OA_ROLE_SYNC_DATABASE"],
        charset="utf8mb4",
        autocommit=True,
        connect_timeout=int(os.getenv("FIN_OPS_OA_ROLE_SYNC_CONNECT_TIMEOUT_SECONDS", "5")),
        read_timeout=int(os.getenv("FIN_OPS_OA_ROLE_SYNC_READ_TIMEOUT_SECONDS", "10")),
        write_timeout=int(os.getenv("FIN_OPS_OA_ROLE_SYNC_WRITE_TIMEOUT_SECONDS", "10")),
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "select menu_id from sys_menu where perms = %s order by menu_id",
                (OA_MENU_PERMISSION,),
            )
            menu_rows = cursor.fetchall()
            cursor.execute(
                "select role_id, role_key from sys_role where role_key in (%s, %s, %s) order by role_key, role_id",
                tuple(ROLE_KEYS.values()),
            )
            role_rows = cursor.fetchall()
            cursor.execute(
                """
                select rm.role_id, rm.menu_id, r.role_key
                from sys_role_menu rm
                join sys_role r on r.role_id = rm.role_id
                join sys_menu m on m.menu_id = rm.menu_id
                where m.perms = %s
                order by rm.menu_id, rm.role_id
                """,
                (OA_MENU_PERMISSION,),
            )
            binding_rows = cursor.fetchall()
            cursor.execute(
                """
                select u.user_name, r.role_key
                from sys_user_role ur
                join sys_user u on u.user_id = ur.user_id
                join sys_role r on r.role_id = ur.role_id
                where r.role_key in (%s, %s, %s)
                order by r.role_key, u.user_name
                """,
                tuple(ROLE_KEYS.values()),
            )
            member_rows = cursor.fetchall()
    finally:
        connection.close()
    tier_by_key = {role_key: tier for tier, role_key in ROLE_KEYS.items()}
    role_ids = {tier: [] for tier in ROLE_TIERS}
    for role_id, role_key in role_rows:
        if str(role_key) in tier_by_key:
            role_ids[tier_by_key[str(role_key)]].append(int(role_id))
    members = {tier: [] for tier in ROLE_TIERS}
    for username, role_key in member_rows:
        if str(role_key) in tier_by_key:
            members[tier_by_key[str(role_key)]].append(str(username))
    return {
        "enabled": True,
        "configured": True,
        "required_permission": required_permission,
        "role_keys_exact": role_keys_exact,
        "menu_ids": [int(row[0]) for row in menu_rows],
        "role_ids": role_ids,
        "bindings": [
            {"role_id": int(role_id), "menu_id": int(menu_id), "role_key": str(role_key)}
            for role_id, menu_id, role_key in binding_rows
        ],
        "members": members,
    }


def _load_json(path: str) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _http_request(
    *,
    base_url: str,
    method: str,
    path: str,
    token: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    request = urllib_request.Request(
        f"{base_url.rstrip('/')}{path}",
        data=body,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            **({"Content-Type": "application/json"} if body is not None else {}),
        },
    )
    started = time.perf_counter()
    try:
        response = urllib_request.urlopen(request, timeout=20)
        status = int(response.status)
        raw = response.read()
        headers = dict(response.headers.items())
    except urllib_error.HTTPError as exc:
        status = int(exc.code)
        raw = exc.read()
        headers = dict(exc.headers.items()) if exc.headers is not None else {}
    elapsed_ms = (time.perf_counter() - started) * 1000
    try:
        decoded = json.loads(raw.decode("utf-8")) if raw else {}
    except (UnicodeDecodeError, ValueError):
        decoded = {}
    return {
        "status": status,
        "payload": decoded if isinstance(decoded, dict) else {},
        "elapsed_ms": round(elapsed_ms, 3),
        "request_id": str(headers.get("X-Request-ID") or headers.get("x-request-id") or ""),
    }


def _expect(response: dict[str, Any], status: int, *, error: str | None = None) -> None:
    if response["status"] != status:
        raise RuntimeError(f"unexpected HTTP status: expected={status}, actual={response['status']}")
    if error is not None and response["payload"].get("error") != error:
        raise RuntimeError(
            f"unexpected HTTP error contract: expected={error}, actual={response['payload'].get('error')}"
        )


def _generic_settings_write_payload(settings: dict[str, Any]) -> dict[str, Any]:
    projects = settings.get("projects") if isinstance(settings.get("projects"), dict) else {}
    oa_import = settings.get("oa_import") if isinstance(settings.get("oa_import"), dict) else {}
    return {
        "completed_project_ids": list(projects.get("completed_project_ids") or []),
        "bank_account_mappings": list(settings.get("bank_account_mappings") or []),
        "workbench_column_layouts": dict(settings.get("workbench_column_layouts") or {}),
        "oa_retention": dict(settings.get("oa_retention") or {}),
        "oa_import": {
            key: oa_import[key]
            for key in ("form_types", "statuses", "attachment_invoice_promotion_mode")
            if key in oa_import
        },
        "oa_invoice_offset": dict(settings.get("oa_invoice_offset") or {}),
    }


def _oa_matches_accounts(oa_roles: dict[str, Any], accounts: list[dict[str, Any]]) -> bool:
    if oa_roles.get("enabled") is not True:
        return True
    members = oa_roles.get("members") if isinstance(oa_roles.get("members"), dict) else {}
    expected = {
        "admin": [PROTECTED_ADMIN_USERNAME],
        "full_access": sorted(
            str(item["username"])
            for item in accounts
            if item.get("access_tier") == "full_access"
        ),
        "read_export_only": sorted(
            str(item["username"])
            for item in accounts
            if item.get("access_tier") == "read_export_only"
        ),
    }
    return all(_strings(members.get(tier)) == values for tier, values in expected.items())


def _latency_summary(values: list[float]) -> dict[str, float | int]:
    ordered = sorted(values)
    p95_index = max(0, min(len(ordered) - 1, int(len(ordered) * 0.95 + 0.999) - 1))
    return {
        "samples": len(ordered),
        "p50_ms": round(statistics.median(ordered), 3),
        "p95_ms": round(ordered[p95_index], 3),
        "max_ms": round(max(ordered), 3),
    }


def _oa_router_contains_finops_menu(payload: object) -> bool:
    if isinstance(payload, list):
        return any(_oa_router_contains_finops_menu(item) for item in payload)
    if not isinstance(payload, dict):
        return False
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    title = str(
        meta.get("title")
        or payload.get("menuName")
        or payload.get("menu_name")
        or payload.get("name")
        or ""
    ).strip()
    path = str(payload.get("path") or "")
    if title == OA_MENU_NAME and "/fin-ops/" in path:
        return True
    return any(_oa_router_contains_finops_menu(value) for value in payload.values())


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
    preflight = _load_json(preflight_path)
    salt = hashlib.sha256(f"settings-access-control-v1\0{release}".encode()).hexdigest()
    report: dict[str, Any] = {
        "contract": "settings-access-control-v1",
        "release": release,
        "status": "fail",
        "preflight_sha256": hashlib.sha256(Path(preflight_path).read_bytes()).hexdigest(),
        "checks": {},
    }
    original_accounts: list[dict[str, Any]] | None = None
    bearer_username = ""
    mutation_request_ids: list[str] = []
    request_latencies: dict[str, list[float]] = {
        "acl_get": [],
        "acl_put": [],
        "session": [],
        "generic_save": [],
        "oa_router": [],
    }
    restore_ok = False
    router_restore_ok = False
    router_visibility: dict[str, bool] = {}

    def http(method: str, path: str, token: str, payload: dict[str, Any] | None = None, *, bucket: str | None = None):
        response = _http_request(base_url=base_url, method=method, path=path, token=token, payload=payload)
        if bucket is not None:
            request_latencies[bucket].append(float(response["elapsed_ms"]))
        return response

    def session(token: str) -> dict[str, Any]:
        response = http("GET", "/api/session/me", token, bucket="session")
        _expect(response, 200)
        return response["payload"]

    def router_visible(token: str) -> bool:
        response = _http_request(
            base_url=oa_base_url,
            method="GET",
            path="/system/menu/getRouters",
            token=token,
        )
        request_latencies["oa_router"].append(float(response["elapsed_ms"]))
        _expect(response, 200)
        if response["payload"].get("code") != 200:
            raise RuntimeError("fresh OA router request did not return code=200")
        return _oa_router_contains_finops_menu(response["payload"].get("data"))

    def acl_get() -> dict[str, Any]:
        response = http("GET", "/api/workbench/settings/access-control", admin_token, bucket="acl_get")
        _expect(response, 200)
        return response["payload"]

    def assign(tier: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        current = acl_get()
        accounts = [
            dict(item)
            for item in list(current.get("accounts") or [])
            if str(item.get("username") or "") != bearer_username
        ]
        if tier in {"full_access", "read_export_only"}:
            accounts.append({"username": bearer_username, "access_tier": tier})
        accounts.sort(key=lambda item: str(item["username"]))
        response = http(
            "PUT",
            "/api/workbench/settings/access-control",
            admin_token,
            {"expected_version": int(current["version"]), "accounts": accounts},
            bucket="acl_put",
        )
        _expect(response, 200)
        if response["payload"].get("changed") is not True:
            raise RuntimeError(f"expected a real ACL transition to {tier}")
        mutation_request_ids.append(response["request_id"])
        return response["payload"], accounts

    try:
        if preflight.get("eligible") is not True or preflight.get("release") != release:
            raise RuntimeError("approved preflight is missing, ineligible, or bound to another release")
        admin_session = session(admin_token)
        bearer_session = session(bearer_token)
        bearer_username = str((bearer_session.get("user") or {}).get("username") or "").strip()
        bearer_fact = _session_fact(bearer_session, salt)
        if not bearer_fact["is_representative_bearer"] or not bearer_fact["oa_menu_permission_present"]:
            raise RuntimeError("dedicated bearer must be permission-bearing YNSYLP006")
        if _session_fact(admin_session, salt)["username_sha256"] != preflight["sessions"]["admin"]["username_sha256"]:
            raise RuntimeError("admin identity hash drifted from approved preflight")
        if _session_fact(bearer_session, salt)["username_sha256"] != preflight["sessions"]["bearer"]["username_sha256"]:
            raise RuntimeError("bearer identity hash drifted from approved preflight")
        if admin_session.get("access_tier") != "admin" or admin_session.get("can_admin_access") is not True:
            raise RuntimeError("admin session contract failed")
        if bearer_session.get("access_tier") != "denied" or bearer_session.get("can_admin_access") is True:
            raise RuntimeError("bearer must start denied and non-admin")
        router_visibility.update(
            {
                "admin": router_visible(admin_token),
                "initial_denied": router_visible(bearer_token),
            }
        )
        if router_visibility != {"admin": True, "initial_denied": False}:
            raise RuntimeError("initial fresh OA router visibility is inconsistent")
        database = collect_database_facts(PostgresConnection(_postgres_settings()))
        if not all(
            (
                database["migration_0132_applied"],
                database["constraint_present"],
                database["constraint_validated"],
            )
        ):
            raise RuntimeError("migration 0132 or its validated CHECK is missing")

        original = acl_get()
        original_accounts = [dict(item) for item in list(original.get("accounts") or [])]
        generic_get = http("GET", "/api/workbench/settings", admin_token)
        _expect(generic_get, 200)
        generic_payload = generic_get["payload"]
        forbidden_keys = {
            "access_control",
            "allowed_usernames",
            "readonly_export_usernames",
            "admin_usernames",
            "full_access_usernames",
            "access_control_version",
        }
        if forbidden_keys.intersection(generic_payload):
            raise RuntimeError("generic settings response leaked access-control fields")

        full_acl, full_accounts = assign("full_access")
        full_session = session(bearer_token)
        if full_session.get("access_tier") != "full_access" or full_session.get("can_mutate_data") is not True:
            raise RuntimeError("full-access session transition failed")
        if not _oa_matches_accounts(collect_oa_role_facts(), full_accounts):
            raise RuntimeError("OA roles do not match the full-access target")
        router_visibility["full_access"] = router_visible(bearer_token)
        if router_visibility["full_access"] is not True:
            raise RuntimeError("full-access fresh OA router is missing the fin-ops menu")
        generic_save = http(
            "POST",
            "/api/workbench/settings",
            bearer_token,
            _generic_settings_write_payload(generic_payload),
            bucket="generic_save",
        )
        _expect(generic_save, 200)
        generic_attack = http(
            "POST",
            "/api/workbench/settings",
            bearer_token,
            {"admin_usernames": [bearer_username]},
        )
        _expect(generic_attack, 400, error="access_control_write_forbidden")
        dedicated_attack = http(
            "PUT",
            "/api/workbench/settings/access-control",
            bearer_token,
            {
                "expected_version": int(full_acl["version"]),
                "accounts": [{"username": bearer_username, "access_tier": "admin"}],
            },
        )
        _expect(dedicated_attack, 403)

        full_admin_guards = {
            "app_health": http("GET", "/api/operations/app-health-dashboard", bearer_token),
            "oa_credentials": http("GET", "/api/workbench/settings/oa-applicant-credentials", bearer_token),
            "data_reset": http("POST", "/api/workbench/settings/data-reset/jobs", bearer_token, {}),
        }
        for response in full_admin_guards.values():
            _expect(response, 403)
        admin_access = {
            "app_health": http("GET", "/api/operations/app-health-dashboard", admin_token),
            "oa_credentials": http("GET", "/api/workbench/settings/oa-applicant-credentials", admin_token),
            "data_reset_validation": http("POST", "/api/workbench/settings/data-reset/jobs", admin_token, {}),
        }
        _expect(admin_access["app_health"], 200)
        _expect(admin_access["oa_credentials"], 200)
        _expect(admin_access["data_reset_validation"], 400, error="invalid_workbench_settings_reset_request")

        _readonly_acl, readonly_accounts = assign("read_export_only")
        readonly_session = session(bearer_token)
        if readonly_session.get("access_tier") != "read_export_only" or readonly_session.get("can_mutate_data") is True:
            raise RuntimeError("read-export session transition failed")
        if not _oa_matches_accounts(collect_oa_role_facts(), readonly_accounts):
            raise RuntimeError("OA roles do not match the read-export target")
        router_visibility["read_export_only"] = router_visible(bearer_token)
        if router_visibility["read_export_only"] is not True:
            raise RuntimeError("read-export fresh OA router is missing the fin-ops menu")
        _expect(
            http("POST", "/api/workbench/settings", bearer_token, _generic_settings_write_payload(generic_payload)),
            403,
        )
        _expect(
            http(
                "PUT",
                "/api/workbench/settings/access-control",
                bearer_token,
                {"expected_version": 1, "accounts": []},
            ),
            403,
        )

        _denied_acl, denied_accounts = assign("denied")
        denied_session = session(bearer_token)
        if denied_session.get("access_tier") != "denied" or denied_session.get("can_access_app") is True:
            raise RuntimeError("denied session transition failed")
        if not _oa_matches_accounts(collect_oa_role_facts(), denied_accounts):
            raise RuntimeError("OA roles do not match the denied target")
        router_visibility["denied"] = router_visible(bearer_token)
        if router_visibility["denied"] is not False:
            raise RuntimeError("denied fresh OA router still exposes the fin-ops menu")
        _expect(http("POST", "/api/workbench/settings", bearer_token, _generic_settings_write_payload(generic_payload)), 403)
        _expect(
            http(
                "PUT",
                "/api/workbench/settings/access-control",
                bearer_token,
                {"expected_version": 1, "accounts": []},
            ),
            403,
        )

        for _ in range(18):
            acl_get()
        database = collect_database_facts(PostgresConnection(_postgres_settings()))
        if not all(
            (
                database["migration_0132_applied"],
                database["constraint_present"],
                database["constraint_validated"],
            )
        ):
            raise RuntimeError("migration 0132 or its validated CHECK is missing")
        connection = PostgresConnection(_postgres_settings())
        audit_matches = 0
        for request_id in mutation_request_ids:
            if request_id and connection.fetch_one(
                "select 1 as present from audit.events where event_type = %s and trace_id = %s limit 1",
                ("settings.access_control.updated", request_id),
            ):
                audit_matches += 1
        if audit_matches != len(mutation_request_ids) or len(mutation_request_ids) != 3:
            raise RuntimeError("durable ACL audit/request-id contract failed")

        latency = {key: _latency_summary(values) for key, values in request_latencies.items() if values}
        if latency["acl_get"]["p95_ms"] > 1000 or latency["acl_put"]["max_ms"] > 5000:
            raise RuntimeError("settings access-control production latency exceeded its release target")
        report["checks"] = {
            "migration_0132_applied": True,
            "constraint_present_and_validated": True,
            "protected_administrator_session": True,
            "approved_identity_hashes_match": True,
            "role_sequence": ["full_access", "read_export_only", "denied"],
            "generic_settings_excludes_acl": True,
            "full_access_generic_save_status": 200,
            "full_access_generic_escalation_status": 400,
            "full_access_dedicated_escalation_status": 403,
            "admin_only_guards": {key: value["status"] for key, value in full_admin_guards.items()},
            "admin_read_paths": {key: value["status"] for key, value in admin_access.items()},
            "oa_matches_each_target": True,
            "oa_router_visibility": dict(router_visibility),
            "durable_audit_request_id_matches": audit_matches,
            "http_call_counts": {key: len(values) for key, values in request_latencies.items()},
            "latency": latency,
        }
        report["bearer_username_sha256"] = _hash_username(bearer_username, salt)
        report["status"] = "pass"
    except Exception as exc:
        report["failure"] = type(exc).__name__
    finally:
        if original_accounts is not None and bearer_username:
            try:
                current = acl_get()
                current_accounts = [dict(item) for item in list(current.get("accounts") or [])]
                if current_accounts != original_accounts:
                    restore = http(
                        "PUT",
                        "/api/workbench/settings/access-control",
                        admin_token,
                        {"expected_version": int(current["version"]), "accounts": original_accounts},
                        bucket="acl_put",
                    )
                    _expect(restore, 200)
                final_acl = acl_get()
                final_session = session(bearer_token)
                restore_ok = (
                    [dict(item) for item in list(final_acl.get("accounts") or [])] == original_accounts
                    and final_session.get("access_tier") == "denied"
                    and _oa_matches_accounts(collect_oa_role_facts(), original_accounts)
                )
                router_restore_ok = restore_ok and not router_visible(bearer_token)
            except Exception:
                restore_ok = False
                router_restore_ok = False
        report["restore"] = {
            "accounts_restored": restore_ok,
            "bearer_final_tier": "denied" if restore_ok else "unverified",
            "oa_restored": restore_ok,
            "oa_router_restored": router_restore_ok,
        }
        if not restore_ok or not router_restore_ok:
            report["status"] = "fail"

    serialized = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    output = Path(output_path)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(serialized, encoding="utf-8")
    temporary.replace(output)
    output.chmod(0o600)
    return report, 0 if report["status"] == "pass" else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only settings access-control production preflight.")
    parser.add_argument("--release", required=True)
    parser.add_argument("--admin-session-json")
    parser.add_argument("--bearer-session-json")
    parser.add_argument("--deployment-facts-json")
    parser.add_argument("--post-deploy", action="store_true")
    parser.add_argument("--database-guard-only", action="store_true")
    parser.add_argument("--preflight-artifact")
    parser.add_argument("--base-url", default="http://127.0.0.1:18001")
    parser.add_argument(
        "--oa-base-url",
        default=(os.getenv("FIN_OPS_OA_BASE_URL") or "").strip(),
    )
    parser.add_argument("--output")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.database_guard_only:
        database = collect_database_facts(PostgresConnection(_postgres_settings()))
        passed = all(
            (
                database["migration_0132_applied"],
                database["constraint_present"],
                database["constraint_validated"],
            )
        )
        report = {
            "contract": "settings-access-control-v1",
            "release": args.release,
            "status": "pass" if passed else "fail",
            "database": {
                "migration_0132_applied": database["migration_0132_applied"],
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
        if not args.oa_base_url:
            parser.error("--post-deploy requires --oa-base-url or FIN_OPS_OA_BASE_URL")
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
        environment={
            "admin_usernames": os.getenv(LEGACY_ADMIN_ENV, "").split(","),
            "retired_admission_env_present": {
                name: name in os.environ for name in RETIRED_ADMISSION_ENVS
            },
        },
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
    if args.json or not args.output:
        print(serialized, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
