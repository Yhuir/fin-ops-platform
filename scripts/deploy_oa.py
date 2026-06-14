from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import argparse
import io
import json
import os
import re
import shlex
import subprocess
import sys
import tarfile
import tempfile


RELEASE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")


@dataclass(slots=True)
class DeploymentConfig:
    mode: str
    host: str
    user: str
    domain: str
    root_dir: Path
    frontend_base_path: str
    remote_frontend_dir: str
    remote_backend_dir: str
    remote_data_dir: str
    remote_service_name: str
    remote_extract_root: str
    remote_releases_dir: str
    release_name: str
    deploy_control_path: str
    keep_releases: int
    skip_build: bool
    skip_pip: bool
    reload_nginx: bool
    activate: bool
    allow_dirty: bool
    replace_release: bool
    dry_run: bool
    runtime_worker_ensure_path: str = "/usr/local/sbin/finops-ensure-runtime-workers"
    remote_min_free_mb: int = 512


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Deploy fin-ops to the OA server.")
    parser.add_argument(
        "--mode",
        choices=("release", "legacy-current"),
        default="release",
        help="Deployment mode. release is the production path; legacy-current preserves the old overwrite deploy.",
    )
    parser.add_argument("--host", default="finops-prod", help="SSH host or alias")
    parser.add_argument("--user", default="finops-deploy", help="SSH user")
    parser.add_argument("--domain", default="www.yn-sourcing.com", help="OA domain")
    parser.add_argument("--frontend-base-path", default="/fin-ops/", help="Frontend base path")
    parser.add_argument("--remote-frontend-dir", default="/www/wwwroot/fin-ops/dist", help="Remote frontend dist directory")
    parser.add_argument("--remote-backend-dir", default="/opt/fin-ops/current/backend", help="Legacy remote backend directory")
    parser.add_argument("--remote-data-dir", default="/opt/fin-ops/data", help="Remote persistent runtime data directory")
    parser.add_argument("--remote-service-name", default="fin-ops.service", help="Legacy remote systemd service name")
    parser.add_argument("--remote-extract-root", default="/tmp/fin-ops-release", help="Legacy remote temporary extract directory")
    parser.add_argument("--remote-releases-dir", default="/opt/fin-ops/releases", help="Remote release directory")
    parser.add_argument("--release-name", default=None, help="Release name. Defaults to branch-sha-timestamp.")
    parser.add_argument(
        "--deploy-control-path",
        default="/usr/local/sbin/finops-deploy-control",
        help="Root-owned server helper used to validate and activate releases.",
    )
    parser.add_argument(
        "--runtime-worker-ensure-path",
        default="/usr/local/sbin/finops-ensure-runtime-workers",
        help="Root-owned server helper used to install, enable and restart runtime worker units.",
    )
    parser.add_argument(
        "--keep-releases",
        type=int,
        default=4,
        help="Number of newest release directories to keep. Active release paths are always preserved.",
    )
    parser.add_argument(
        "--remote-min-free-mb",
        type=int,
        default=512,
        help="Minimum free space required on the remote release filesystem before uploading a release.",
    )
    parser.add_argument("--skip-build", action="store_true", help="Skip local frontend build")
    parser.add_argument("--skip-pip", action="store_true", help="Legacy mode only: skip remote pip install")
    parser.add_argument("--reload-nginx", action="store_true", help="Legacy mode only: reload nginx after deploy")
    parser.add_argument("--no-activate", action="store_true", help="Upload and validate the release without activating it")
    parser.add_argument("--allow-dirty", action="store_true", help="Allow release deploy from a dirty git worktree")
    parser.add_argument("--replace-release", action="store_true", help="Replace an existing remote release directory with the same name")
    parser.add_argument("--dry-run", action="store_true", help="Print commands without executing")
    return parser


def normalize_base_path(value: str) -> str:
    trimmed = value.strip() or "/"
    if trimmed == "/":
        return "/"
    with_leading = trimmed if trimmed.startswith("/") else f"/{trimmed}"
    return with_leading if with_leading.endswith("/") else f"{with_leading}/"


def build_config(args: argparse.Namespace, *, root_dir: Path) -> DeploymentConfig:
    release_name = args.release_name or build_default_release_name(root_dir)
    validate_release_name(release_name)
    if args.keep_releases < 0:
        raise ValueError("--keep-releases must be >= 0")
    if args.remote_min_free_mb < 0:
        raise ValueError("--remote-min-free-mb must be >= 0")
    return DeploymentConfig(
        mode=args.mode,
        host=args.host,
        user=args.user,
        domain=args.domain,
        root_dir=root_dir,
        frontend_base_path=normalize_base_path(args.frontend_base_path),
        remote_frontend_dir=args.remote_frontend_dir.rstrip("/") or "/www/wwwroot/fin-ops/dist",
        remote_backend_dir=args.remote_backend_dir.rstrip("/") or "/opt/fin-ops/current/backend",
        remote_data_dir=args.remote_data_dir.rstrip("/") or "/opt/fin-ops/data",
        remote_service_name=args.remote_service_name,
        remote_extract_root=args.remote_extract_root.rstrip("/") or "/tmp/fin-ops-release",
        remote_releases_dir=args.remote_releases_dir.rstrip("/") or "/opt/fin-ops/releases",
        release_name=release_name,
        deploy_control_path=args.deploy_control_path,
        runtime_worker_ensure_path=args.runtime_worker_ensure_path,
        keep_releases=int(args.keep_releases),
        skip_build=bool(args.skip_build),
        skip_pip=bool(args.skip_pip),
        reload_nginx=bool(args.reload_nginx),
        activate=not bool(args.no_activate),
        allow_dirty=bool(args.allow_dirty),
        replace_release=bool(args.replace_release),
        dry_run=bool(args.dry_run),
        remote_min_free_mb=int(args.remote_min_free_mb),
    )


def build_default_release_name(root_dir: Path) -> str:
    branch = _git_output(root_dir, "rev-parse", "--abbrev-ref", "HEAD") or "manual"
    short_sha = _git_output(root_dir, "rev-parse", "--short=8", "HEAD") or "nogit"
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    prefix = sanitize_release_name_part(branch)
    return f"{prefix}-{short_sha}-{timestamp}"


def sanitize_release_name_part(value: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip())
    sanitized = sanitized.strip(".-_")
    return sanitized or "manual"


def validate_release_name(value: str) -> None:
    if not RELEASE_NAME_PATTERN.fullmatch(value):
        raise ValueError(f"invalid release name: {value!r}; use only letters, numbers, '.', '_' and '-'")


def _git_output(root_dir: Path, *args: str) -> str | None:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=root_dir,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return completed.stdout.strip()


def ensure_clean_git_tree(config: DeploymentConfig) -> None:
    if config.mode != "release" or config.allow_dirty or config.dry_run:
        return
    status = _git_output(config.root_dir, "status", "--porcelain")
    if status is None:
        raise RuntimeError("refusing release deploy because git status is unavailable; pass --allow-dirty to override")
    if status.strip():
        raise RuntimeError(
            "refusing release deploy from a dirty worktree; commit/stash changes or pass --allow-dirty"
        )


def build_release_remote_deploy_script(config: DeploymentConfig) -> str:
    release_dir = str(Path(config.remote_releases_dir) / config.release_name)
    quoted_release_name = shlex.quote(config.release_name)
    quoted_release_dir = shlex.quote(release_dir)
    quoted_releases_dir = shlex.quote(config.remote_releases_dir)
    quoted_deploy_control = shlex.quote(config.deploy_control_path)
    quoted_runtime_worker_ensure = shlex.quote(config.runtime_worker_ensure_path)
    commands = [
        "set -euo pipefail",
        build_remote_failure_trap(),
        mark_remote_deploy_step("initialize release variables"),
        f"RELEASE_NAME={quoted_release_name}",
        f"RELEASES_DIR={quoted_releases_dir}",
        f"RELEASE_DIR={quoted_release_dir}",
        f"DEPLOY_CONTROL={quoted_deploy_control}",
        f"KEEP_RELEASES={int(config.keep_releases)}",
        f"REMOTE_MIN_FREE_MB={int(config.remote_min_free_mb)}",
        mark_remote_deploy_step("validate release name"),
        'case "$RELEASE_NAME" in *[!A-Za-z0-9._-]*|"") echo "invalid release name: $RELEASE_NAME" >&2; exit 64 ;; esac',
        mark_remote_deploy_step("verify deploy-control contract"),
        build_deploy_control_contract_check(),
        mark_remote_deploy_step("ensure releases directory"),
        'mkdir -p "$RELEASES_DIR"',
    ]
    if config.activate and config.keep_releases > 0:
        commands.append(mark_remote_deploy_step("preflight cleanup old releases"))
        commands.append(f"sudo -n {quoted_deploy_control} cleanup-releases --keep {int(config.keep_releases)}")
    commands.extend(
        [
            mark_remote_deploy_step("storage preflight"),
            build_release_storage_preflight_check(),
            mark_remote_deploy_step("prepare release directory"),
        ]
    )
    if config.replace_release:
        commands.append('rm -rf -- "$RELEASE_DIR"')
    else:
        commands.append('if [ -e "$RELEASE_DIR" ]; then echo "release already exists: $RELEASE_DIR" >&2; exit 64; fi')
    commands.extend(
        [
            'mkdir -p "$RELEASE_DIR"',
            mark_remote_deploy_step("extract release archive"),
            'tar -xzf - -C "$RELEASE_DIR"',
            mark_remote_deploy_step("validate release layout"),
            'test -d "$RELEASE_DIR/src/backend/src"',
            'test -f "$RELEASE_DIR/src/backend/requirements.txt"',
            'test -f "$RELEASE_DIR/src/web/dist/index.html"',
            mark_remote_deploy_step("deploy-control check-release"),
            f"sudo -n {quoted_deploy_control} check-release {quoted_release_name}",
        ]
    )
    if config.activate:
        commands.extend(
            [
                mark_remote_deploy_step("deploy-control activate"),
                f"sudo -n {quoted_deploy_control} activate {quoted_release_name}",
                mark_remote_deploy_step("backend readiness check"),
                build_backend_readiness_check(),
                mark_remote_deploy_step("deploy-control status"),
                f"sudo -n {quoted_deploy_control} status",
                mark_remote_deploy_step("runtime worker ensure"),
                f'sudo -n {quoted_runtime_worker_ensure} "$RELEASE_DIR/src"',
                mark_remote_deploy_step("frontend hash check"),
                build_frontend_hash_check(config),
                mark_remote_deploy_step("public session route check"),
                build_public_api_route_check(config),
            ]
        )
        if config.keep_releases > 0:
            commands.append(mark_remote_deploy_step("cleanup old releases"))
            commands.append(f"sudo -n {quoted_deploy_control} cleanup-releases --keep {int(config.keep_releases)}")
        if config.reload_nginx:
            commands.append('echo "release mode does not reload nginx; static files do not require nginx reload" >&2')
    else:
        commands.append(mark_remote_deploy_step("release upload validated"))
        commands.append('echo "release uploaded and validated; activation skipped: $RELEASE_NAME"')
    return "\n".join(commands) + "\n"


def build_remote_failure_trap() -> str:
    return "\n".join(
        [
            "DEPLOY_STEP=bootstrap",
            "trap 'status=$?; printf \"finops remote deploy failed at step: %s (exit=%s)\\n\" \"${DEPLOY_STEP:-unknown}\" \"$status\" >&2; exit \"$status\"' ERR",
        ]
    )


def mark_remote_deploy_step(step: str) -> str:
    return "\n".join(
        [
            f"DEPLOY_STEP={shlex.quote(step)}",
            'printf "== finops deploy step: %s ==\\n" "$DEPLOY_STEP" >&2',
        ]
    )


def build_deploy_control_contract_check() -> str:
    return "\n".join(
        [
            "verify_finops_deploy_control_contract() {",
            '  if [ ! -x "$DEPLOY_CONTROL" ]; then',
            '    printf \'deploy-control helper is missing or not executable: %s\\n\' "$DEPLOY_CONTROL" >&2',
            "    exit 68",
            "  fi",
            '  if [ -r "$DEPLOY_CONTROL" ]; then',
            "    if grep -q '/root/fin_ops_stage23_postgres_runtime.env' \"$DEPLOY_CONTROL\"; then",
            "      printf '%s\\n' 'deploy-control helper still loads the retired /root PostgreSQL env; install deploy/oa/bin/finops-deploy-control.sh before activating releases' >&2",
            "      exit 68",
            "    fi",
            "    if ! grep -q 'fin-ops.secrets.env' \"$DEPLOY_CONTROL\"; then",
            "      printf '%s\\n' 'deploy-control helper does not load fin-ops.secrets.env; install deploy/oa/bin/finops-deploy-control.sh before activating releases' >&2",
            "      exit 68",
            "    fi",
            "    if ! grep -q '^EnvironmentFile=$' \"$DEPLOY_CONTROL\"; then",
            "      printf '%s\\n' 'deploy-control helper does not reset inherited EnvironmentFile entries; install deploy/oa/bin/finops-deploy-control.sh before activating releases' >&2",
            "      exit 68",
            "    fi",
            "    if ! grep -q 'archive_legacy_current' \"$DEPLOY_CONTROL\"; then",
            "      printf '%s\\n' 'deploy-control helper does not archive legacy /opt/fin-ops/current; install deploy/oa/bin/finops-deploy-control.sh before activating releases' >&2",
            "      exit 68",
            "    fi",
            "    if ! grep -q 'missing OA session runtime env' \"$DEPLOY_CONTROL\"; then",
            "      printf '%s\\n' 'deploy-control helper does not enforce OA session env; install deploy/oa/bin/finops-deploy-control.sh before activating releases' >&2",
            "      exit 68",
            "    fi",
            "    if ! grep -q 'readiness_status' \"$DEPLOY_CONTROL\"; then",
            "      printf '%s\\n' 'deploy-control helper does not tolerate non-ready worker readiness polls under set -e; install deploy/oa/bin/finops-deploy-control.sh before activating releases' >&2",
            "      exit 68",
            "    fi",
            "    if ! grep -q -- '--dependency-not-fresh-delay-seconds' \"$DEPLOY_CONTROL\"; then",
            "      printf '%s\\n' 'deploy-control helper does not preserve worker dependency-not-fresh delay in release drop-ins; install deploy/oa/bin/finops-deploy-control.sh before activating releases' >&2",
            "      exit 68",
            "    fi",
            "  fi",
            "}",
            "verify_finops_deploy_control_contract",
        ]
    )


def build_release_storage_preflight_check() -> str:
    return "\n".join(
        [
            "assert_finops_release_storage() {",
            "  required_mb=\"$1\"",
            "  path=\"$2\"",
            "  if [ \"$required_mb\" -le 0 ]; then",
            "    return 0",
            "  fi",
            "  available_mb=$(df -Pm -- \"$path\" | awk 'NR==2 {print $4}')",
            "  case \"$available_mb\" in ''|*[!0-9]*)",
            "    printf 'unable to read available storage for release path: %s\\n' \"$path\" >&2",
            "    df -h -- \"$path\" >&2 || true",
            "    exit 69",
            "    ;;",
            "  esac",
            "  printf 'release storage available: path=%s available_mb=%s required_mb=%s\\n' \"$path\" \"$available_mb\" \"$required_mb\" >&2",
            "  if [ \"$available_mb\" -lt \"$required_mb\" ]; then",
            "    printf 'insufficient storage for release deploy: path=%s available_mb=%s required_mb=%s\\n' \"$path\" \"$available_mb\" \"$required_mb\" >&2",
            "    df -h -- \"$path\" >&2 || true",
            "    du -sh -- \"$RELEASES_DIR\" /opt/fin-ops /var/log /var/log/journal 2>/dev/null >&2 || true",
            "    exit 69",
            "  fi",
            "}",
            'assert_finops_release_storage "$REMOTE_MIN_FREE_MB" "$RELEASES_DIR"',
        ]
    )


def build_frontend_hash_check(config: DeploymentConfig) -> str:
    remote_frontend_index = str(Path(config.remote_frontend_dir) / "index.html")
    return "\n".join(
        [
            "release_index_hash=$(sha256sum \"$RELEASE_DIR/src/web/dist/index.html\" | awk '{print $1}')",
            (
                f"live_index_hash=$(sha256sum {shlex.quote(remote_frontend_index)} 2>/dev/null "
                "| awk '{print $1}' || true)"
            ),
            (
                'if [ -n "$live_index_hash" ] && [ "$release_index_hash" != "$live_index_hash" ]; then '
                'echo "frontend dist hash mismatch after activation; deploy-control must publish web/dist" >&2; '
                "exit 65; "
                "fi"
            ),
        ]
    )


def build_backend_readiness_check() -> str:
    return "\n".join(
        [
            "wait_finops_backend_ready() {",
            "  deadline=$((SECONDS + 90))",
            "  last_health=\"\"",
            "  while [ \"$SECONDS\" -lt \"$deadline\" ]; do",
            "    health=$(curl -fsS --max-time 5 http://127.0.0.1:18001/health/ready 2>&1 || true)",
            (
                "    if printf '%s' \"$health\" | "
                "python3 -c 'import json, sys; data = json.load(sys.stdin); "
                "sys.exit(0 if data.get(\"status\") == \"ready\" else 1)' 2>/dev/null; then"
            ),
            "      return 0",
            "    fi",
            "    last_health=\"$health\"",
            "    sleep 2",
            "  done",
            "  echo \"backend did not become ready after release activation\" >&2",
            "  printf '%s\\n' \"$last_health\" >&2",
            "  exit 67",
            "}",
            "wait_finops_backend_ready",
        ]
    )


def build_public_api_route_check(config: DeploymentConfig) -> str:
    quoted_domain = shlex.quote(config.domain)
    return "\n".join(
        [
            f"PUBLIC_DOMAIN={quoted_domain}",
            "check_finops_session_route() {",
            "  route=\"$1\"",
            "  route_deadline=$((SECONDS + 60))",
            "  headers=\"\"",
            "  status=\"\"",
            "  content_type=\"\"",
            "  while :; do",
            "    headers=$(curl -skI --max-time 10 \"https://${PUBLIC_DOMAIN}${route}\" || true)",
            "    status=$(printf '%s\\n' \"$headers\" | awk '/^HTTP\\// { code=$2 } END { print code }')",
            (
                "    content_type=$(printf '%s\\n' \"$headers\" | "
                "awk 'BEGIN{IGNORECASE=1} /^content-type:/ { sub(/^[^:]+:[[:space:]]*/, \"\"); print; exit }')"
            ),
            "    if [ \"$status\" = \"401\" ] && printf '%s' \"$content_type\" | grep -qi 'application/json'; then",
            "      return 0",
            "    fi",
            "    if [ \"$SECONDS\" -ge \"$route_deadline\" ]; then",
            "      printf 'session API route is not proxied as JSON: %s status=%s content-type=%s\\n' \"$route\" \"$status\" \"$content_type\" >&2",
            "      printf '%s\\n' \"$headers\" >&2",
            "      exit 66",
            "    fi",
            "    sleep 2",
            "  done",
            "}",
            "check_finops_session_route /fin-ops-api/api/session/me",
            "check_finops_session_route /fin-ops/api/session/me",
        ]
    )


def build_legacy_remote_deploy_script(config: DeploymentConfig) -> str:
    legacy_data_dir = str(Path(config.remote_backend_dir) / ".runtime" / "fin_ops_platform")
    service_dropin_dir = f"/etc/systemd/system/{config.remote_service_name}.d"
    service_dropin_path = f"{service_dropin_dir}/10-fin-ops-env.conf"
    commands = [
        "set -euo pipefail",
        f"REMOTE_ROOT={shlex.quote(config.remote_extract_root)}",
        f"REMOTE_DATA_DIR={shlex.quote(config.remote_data_dir)}",
        'rm -rf "$REMOTE_ROOT"',
        'mkdir -p "$REMOTE_ROOT"',
        'tar -xzf - -C "$REMOTE_ROOT"',
        f"mkdir -p {shlex.quote(str(Path(config.remote_frontend_dir).parent))}",
        f"mkdir -p {shlex.quote(str(Path(config.remote_backend_dir).parent))}",
        'mkdir -p "$REMOTE_DATA_DIR"',
        f"if [ -d {shlex.quote(legacy_data_dir)} ]; then cp -an {shlex.quote(legacy_data_dir)}/. \"$REMOTE_DATA_DIR\"/; fi",
        f"rm -rf {shlex.quote(config.remote_frontend_dir)}",
        f"rm -rf {shlex.quote(config.remote_backend_dir)}",
        f"mv \"$REMOTE_ROOT\"/dist {shlex.quote(config.remote_frontend_dir)}",
        f"mv \"$REMOTE_ROOT\"/backend {shlex.quote(config.remote_backend_dir)}",
        "if [ ! -d /opt/fin-ops/venv ]; then python3 -m venv /opt/fin-ops/venv; fi",
        f"mkdir -p {shlex.quote(service_dropin_dir)}",
        (
            f"cat > {shlex.quote(service_dropin_path)} <<'EOF'\n"
            "[Service]\n"
            f"Environment=FIN_OPS_DATA_DIR={config.remote_data_dir}\n"
            "Environment=FIN_OPS_OA_BASE_URL=https://www.yn-sourcing.com/oa-api\n"
            "Environment=FIN_OPS_ETC_OA_BASE_URL=https://www.yn-sourcing.com/oa-api\n"
            "Environment=FIN_OPS_ETC_OA_FILE_UPLOAD_PATH=/file/upload\n"
            "Environment=FIN_OPS_ETC_OA_FORM_DRAFT_PATH=/forms/form/{form_id}/records/record\n"
            "Environment=FIN_OPS_ETC_OA_DRAFT_URL_TEMPLATE=https://www.yn-sourcing.com/oa/#/normal/forms/form/{form_id}?formId={form_id}&id={draft_id}\n"
            "EOF"
        ),
        "systemctl daemon-reload",
    ]
    if not config.skip_pip:
        commands.append(
            f"/opt/fin-ops/venv/bin/pip install -r {shlex.quote(config.remote_backend_dir + '/requirements.txt')}"
        )
    commands.append(f"systemctl restart {shlex.quote(config.remote_service_name)}")
    commands.append(f"systemctl status {shlex.quote(config.remote_service_name)} --no-pager -l | head -n 20")
    if config.reload_nginx:
        commands.append("nginx -t")
        commands.append("nginx -s reload")
    return "\n".join(commands) + "\n"


def build_remote_deploy_script(config: DeploymentConfig) -> str:
    if config.mode == "release":
        return build_release_remote_deploy_script(config)
    return build_legacy_remote_deploy_script(config)


def build_ssh_base_command(config: DeploymentConfig) -> list[str]:
    return [
        "ssh",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        "ControlMaster=no",
        f"{config.user}@{config.host}",
    ]


def build_remote_command(config: DeploymentConfig, remote_script: str) -> list[str]:
    return build_ssh_base_command(config) + [f"bash -lc {shlex.quote(remote_script)}"]


def run_command(command: list[str], *, dry_run: bool, input_bytes: bytes | None = None) -> None:
    if dry_run:
        printable = " ".join(shlex.quote(part) for part in command)
        print(printable)
        return
    subprocess.run(command, check=True, input=input_bytes)


def create_release_archive(config: DeploymentConfig) -> Path:
    if config.mode == "legacy-current":
        return create_legacy_release_archive(config)
    return create_versioned_release_archive(config)


def create_versioned_release_archive(config: DeploymentConfig) -> Path:
    frontend_dist = config.root_dir / "web" / "dist"
    backend_dir = config.root_dir / "backend"
    scripts_dir = config.root_dir / "scripts"
    deploy_oa_dir = config.root_dir / "deploy" / "oa"
    if not frontend_dist.exists():
        raise FileNotFoundError(f"frontend dist not found: {frontend_dist}")
    if not backend_dir.exists():
        raise FileNotFoundError(f"backend dir not found: {backend_dir}")

    temp_dir = Path(tempfile.mkdtemp(prefix="fin-ops-release-"))
    archive_path = temp_dir / "release.tar.gz"
    metadata = build_release_metadata(config)
    with tarfile.open(archive_path, "w:gz") as archive:
        archive.add(backend_dir, arcname="src/backend", filter=_tar_filter)
        archive.add(frontend_dist, arcname="src/web/dist", filter=_tar_filter)
        if scripts_dir.exists():
            archive.add(scripts_dir, arcname="src/scripts", filter=_tar_filter)
        if deploy_oa_dir.exists():
            archive.add(deploy_oa_dir, arcname="src/deploy/oa", filter=_tar_filter)
        for filename in ("README.md", "ARCHITECTURE.md", "AGENTS.md"):
            path = config.root_dir / filename
            if path.exists():
                archive.add(path, arcname=f"src/{filename}", filter=_tar_filter)
        add_bytes_to_tar(
            archive,
            "src/RELEASE.json",
            json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8"),
        )
    return archive_path


def create_legacy_release_archive(config: DeploymentConfig) -> Path:
    frontend_dist = config.root_dir / "web" / "dist"
    backend_dir = config.root_dir / "backend"
    if not frontend_dist.exists():
        raise FileNotFoundError(f"frontend dist not found: {frontend_dist}")
    if not backend_dir.exists():
        raise FileNotFoundError(f"backend dir not found: {backend_dir}")

    temp_dir = Path(tempfile.mkdtemp(prefix="fin-ops-deploy-"))
    archive_path = temp_dir / "release.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        archive.add(frontend_dist, arcname="dist", filter=_tar_filter)
        archive.add(backend_dir, arcname="backend", filter=_tar_filter)
    return archive_path


def build_release_metadata(config: DeploymentConfig) -> dict[str, object]:
    return {
        "release_name": config.release_name,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "git_branch": _git_output(config.root_dir, "rev-parse", "--abbrev-ref", "HEAD"),
        "git_commit": _git_output(config.root_dir, "rev-parse", "HEAD"),
        "git_status_porcelain": _git_output(config.root_dir, "status", "--porcelain"),
        "frontend_base_path": config.frontend_base_path,
        "mode": config.mode,
    }


def add_bytes_to_tar(archive: tarfile.TarFile, arcname: str, data: bytes) -> None:
    info = tarfile.TarInfo(name=arcname)
    info.size = len(data)
    info.mode = 0o644
    info.mtime = int(datetime.now().timestamp())
    archive.addfile(info, io.BytesIO(data))


def _tar_filter(tar_info: tarfile.TarInfo) -> tarfile.TarInfo | None:
    name = tar_info.name
    parts = Path(name).parts
    excluded_parts = {
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".runtime",
        ".venv",
        "__pycache__",
        "node_modules",
        "venv",
    }
    if any(part in excluded_parts for part in parts):
        return None
    if name.endswith((".pyc", ".pyo", ".DS_Store")):
        return None
    return tar_info


def build_frontend(config: DeploymentConfig) -> None:
    if config.skip_build:
        return
    subprocess.run(
        ["npm", "run", "build"],
        cwd=config.root_dir / "web",
        check=True,
        env={
            **dict(os.environ),
            "VITE_APP_BASE_PATH": config.frontend_base_path,
        },
    )


def deploy(config: DeploymentConfig) -> None:
    ensure_clean_git_tree(config)
    build_frontend(config)
    archive_path = create_release_archive(config)
    remote_script = build_remote_deploy_script(config)
    archive_bytes = archive_path.read_bytes()
    remote_command = build_remote_command(config, remote_script)
    run_command(remote_command, dry_run=config.dry_run, input_bytes=archive_bytes)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config = build_config(args, root_dir=Path(__file__).resolve().parents[1])
    deploy(config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
