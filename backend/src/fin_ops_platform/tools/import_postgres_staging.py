from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from fin_ops_platform.postgres.migrate import MigrationError, database_url_from_env_or_arg, run_psql
from fin_ops_platform.tools.export_manifest import safe_jsonable, sha256_file


REQUIRED_MIGRATIONS = ("0001", "0002", "0003", "0004", "0005", "0006", "0007", "0008")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import stage 03 Mongo export artifacts into PostgreSQL staging.")
    parser.add_argument("--export-dir", required=True, type=Path)
    parser.add_argument("--database-url")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--replace-existing-staging",
        action="store_true",
        help="Delete existing staging rows before import. Use only after restore gate when importing production.",
    )
    args = parser.parse_args(argv)
    try:
        result = import_postgres_staging(
            export_dir=args.export_dir,
            database_url=args.database_url,
            dry_run=args.dry_run,
            replace_existing_staging=args.replace_existing_staging,
        )
    except Exception as exc:  # noqa: BLE001 - CLI boundary with sanitized output.
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def import_postgres_staging(
    *,
    export_dir: Path,
    database_url: str | None = None,
    dry_run: bool,
    replace_existing_staging: bool = False,
) -> dict[str, Any]:
    manifest = load_and_validate_manifest(export_dir)
    ndjson_files = sorted(name for name in manifest["files"] if name.endswith(".ndjson"))
    total_records = int(sum(int(manifest["files"][name]["record_count"]) for name in ndjson_files))
    plan = {
        "export_id": manifest["export_id"],
        "export_dir": str(export_dir),
        "source_database": manifest["source_database"],
        "files": ndjson_files,
        "total_records": total_records,
        "dry_run": dry_run,
        "replace_existing_staging": replace_existing_staging,
    }
    if dry_run:
        return plan

    resolved_database_url = database_url_from_env_or_arg(database_url)
    assert_required_migrations(resolved_database_url)

    existing = run_psql(
        resolved_database_url,
        sql=f"select coalesce((select manifest->>'manifest_sha256' from staging.mongo_exports where export_id = {sql_literal(manifest['export_id'])}), '');",
    ).strip()
    if existing:
        if existing == manifest.get("manifest_sha256"):
            return {**plan, "status": "skipped", "reason": "export_already_imported"}
        raise MigrationError("Existing staging export has a different manifest checksum.")

    statements: list[str] = ["begin;", "select pg_advisory_xact_lock(hashtext('fin_ops_platform_stage03_import'));"]
    if replace_existing_staging:
        statements.extend(
            [
                "delete from staging.mongo_raw_records;",
                "delete from staging.mongo_exports;",
            ]
        )
    statements.append(
        """
insert into staging.mongo_exports(export_id, source_database, source_backup_archive, source_backup_sha256, status, manifest, raw_payload)
values ({export_id}, {source_database}, {archive}, {backup_sha}, 'imported', {manifest}::jsonb, {raw_payload}::jsonb);
""".format(
            export_id=sql_literal(manifest["export_id"]),
            source_database=sql_literal(manifest["source_database"]),
            archive=sql_literal(manifest.get("app_backup_archive")),
            backup_sha=sql_literal(manifest.get("app_backup_sha256")),
            manifest=sql_literal(json.dumps(manifest, ensure_ascii=False, separators=(",", ":"))),
            raw_payload=sql_literal(json.dumps({"stage": "03", "source_mode": manifest.get("source_mode")}, ensure_ascii=False)),
        )
    )

    for values in iter_insert_value_chunks(export_dir, ndjson_files, chunk_size=250):
        statements.append(
            """
insert into staging.mongo_raw_records(export_id, source_collection, legacy_mongo_id, record_type, normalized_payload, raw_payload)
values
{values};
""".format(values=",\n".join(values))
        )
    statements.append(
        f"""
do $$
declare actual_count bigint;
begin
  select count(*) into actual_count
  from staging.mongo_raw_records r
  join staging.mongo_exports e on e.id = r.export_id
  where e.export_id = {sql_literal(manifest["export_id"])};
  if actual_count <> {total_records} then
    raise exception 'staging count mismatch: expected %, actual %', {total_records}, actual_count;
  end if;
end $$;
commit;
"""
    )
    run_psql(resolved_database_url, sql="\n".join(statements))
    return {**plan, "status": "imported"}


def load_and_validate_manifest(export_dir: Path) -> dict[str, Any]:
    manifest_path = export_dir / "manifest.json"
    if not manifest_path.exists():
        raise MigrationError(f"Missing manifest: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("status") != "completed":
        raise MigrationError("Export manifest is not completed.")
    for name, metadata in manifest.get("files", {}).items():
        path = export_dir / name
        if not path.exists():
            raise MigrationError(f"Missing export file: {name}")
        actual_sha = sha256_file(path)
        if actual_sha != metadata.get("sha256"):
            raise MigrationError(f"Checksum mismatch for export file: {name}")
    recorded_manifest_sha = manifest.get("manifest_sha256")
    if recorded_manifest_sha and manifest_payload_sha256(manifest) != recorded_manifest_sha:
        raise MigrationError("Manifest checksum drift detected.")
    return manifest


def manifest_payload_sha256(manifest: dict[str, Any]) -> str:
    import hashlib

    payload = dict(manifest)
    payload.pop("manifest_sha256", None)
    encoded = (
        json.dumps(safe_jsonable(payload, allow_binary_metadata=True), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def assert_required_migrations(database_url: str) -> None:
    required_versions_sql = ",".join(sql_literal(version) for version in REQUIRED_MIGRATIONS)
    versions = run_psql(
        database_url,
        sql=f"""
select coalesce(string_agg(version, ',' order by version), '')
from public.schema_migrations
where version in ({required_versions_sql});
""",
    ).strip()
    actual = tuple(item for item in versions.split(",") if item)
    if actual != REQUIRED_MIGRATIONS:
        raise MigrationError(
            "PostgreSQL schema migrations "
            + ",".join(REQUIRED_MIGRATIONS)
            + " are required before staging import."
        )


def iter_insert_value_chunks(export_dir: Path, filenames: list[str], *, chunk_size: int) -> list[list[str]]:
    chunks: list[list[str]] = []
    current: list[str] = []
    for filename in filenames:
        with (export_dir / filename).open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                record = json.loads(line)
                current.append(sql_record_values(record))
                if len(current) >= chunk_size:
                    chunks.append(current)
                    current = []
    if current:
        chunks.append(current)
    return chunks


def sql_record_values(record: dict[str, Any]) -> str:
    normalized_payload = json.dumps(record.get("normalized_payload") or {}, ensure_ascii=False, separators=(",", ":"))
    raw_payload = json.dumps(record.get("raw_payload") or {}, ensure_ascii=False, separators=(",", ":"))
    return "((select id from staging.mongo_exports where export_id = {export_id}), {source_collection}, {legacy_mongo_id}, {record_type}, {normalized_payload}::jsonb, {raw_payload}::jsonb)".format(
        export_id=sql_literal(record["export_id"]),
        source_collection=sql_literal(record["source_collection"]),
        legacy_mongo_id=sql_literal(record.get("legacy_mongo_id")),
        record_type=sql_literal(record.get("record_type")),
        normalized_payload=sql_literal(normalized_payload),
        raw_payload=sql_literal(raw_payload),
    )


def sql_literal(value: object) -> str:
    if value is None:
        return "null"
    return "'" + str(value).replace("'", "''") + "'"


if __name__ == "__main__":
    raise SystemExit(main())
