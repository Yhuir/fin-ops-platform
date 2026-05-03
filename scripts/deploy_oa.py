from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import argparse
import os
import shlex
import subprocess
import sys
import tarfile
import tempfile


@dataclass(slots=True)
class DeploymentConfig:
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
    skip_build: bool
    skip_pip: bool
    reload_nginx: bool
    dry_run: bool


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Deploy fin-ops to the OA server.")
    parser.add_argument("--host", default="139.155.5.132", help="OA server host")
    parser.add_argument("--user", default="root", help="SSH user")
    parser.add_argument("--domain", default="www.yn-sourcing.com", help="OA domain")
    parser.add_argument("--frontend-base-path", default="/fin-ops/", help="Frontend base path")
    parser.add_argument("--remote-frontend-dir", default="/www/wwwroot/fin-ops/dist", help="Remote frontend dist directory")
    parser.add_argument("--remote-backend-dir", default="/opt/fin-ops/current/backend", help="Remote backend directory")
    parser.add_argument("--remote-data-dir", default="/opt/fin-ops/data", help="Remote persistent runtime data directory")
    parser.add_argument("--remote-service-name", default="fin-ops.service", help="Remote systemd service name")
    parser.add_argument("--remote-extract-root", default="/tmp/fin-ops-release", help="Remote temporary extract directory")
    parser.add_argument("--skip-build", action="store_true", help="Skip local frontend build")
    parser.add_argument("--skip-pip", action="store_true", help="Skip remote pip install")
    parser.add_argument("--reload-nginx", action="store_true", help="Reload nginx after deploy")
    parser.add_argument("--dry-run", action="store_true", help="Print commands without executing")
    return parser


def normalize_base_path(value: str) -> str:
    trimmed = value.strip() or "/"
    if trimmed == "/":
        return "/"
    with_leading = trimmed if trimmed.startswith("/") else f"/{trimmed}"
    return with_leading if with_leading.endswith("/") else f"{with_leading}/"


def build_config(args: argparse.Namespace, *, root_dir: Path) -> DeploymentConfig:
    return DeploymentConfig(
        host=args.host,
        user=args.user,
        domain=args.domain,
        root_dir=root_dir,
        frontend_base_path=normalize_base_path(args.frontend_base_path),
        remote_frontend_dir=args.remote_frontend_dir,
        remote_backend_dir=args.remote_backend_dir,
        remote_data_dir=args.remote_data_dir.rstrip("/") or "/opt/fin-ops/data",
        remote_service_name=args.remote_service_name,
        remote_extract_root=args.remote_extract_root.rstrip("/") or "/tmp/fin-ops-release",
        skip_build=bool(args.skip_build),
        skip_pip=bool(args.skip_pip),
        reload_nginx=bool(args.reload_nginx),
        dry_run=bool(args.dry_run),
    )


def build_remote_deploy_script(config: DeploymentConfig) -> str:
    legacy_data_dir = str(Path(config.remote_backend_dir) / ".runtime" / "fin_ops_platform")
    service_dropin_dir = f"/etc/systemd/system/{config.remote_service_name}.d"
    service_dropin_path = f"{service_dropin_dir}/10-fin-ops-env.conf"
    commands = [
        "set -euo pipefail",
        f"REMOTE_ROOT={shlex.quote(config.remote_extract_root)}",
        f"REMOTE_DATA_DIR={shlex.quote(config.remote_data_dir)}",
        "rm -rf \"$REMOTE_ROOT\"",
        "mkdir -p \"$REMOTE_ROOT\"",
        "tar -xzf - -C \"$REMOTE_ROOT\"",
        f"mkdir -p {shlex.quote(str(Path(config.remote_frontend_dir).parent))}",
        f"mkdir -p {shlex.quote(str(Path(config.remote_backend_dir).parent))}",
        "mkdir -p \"$REMOTE_DATA_DIR\"",
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
            "Environment=FIN_OPS_OA_BASE_URL=https://www.yn-sourcing.com/prod-api\n"
            "Environment=FIN_OPS_ETC_OA_BASE_URL=https://www.yn-sourcing.com/prod-api\n"
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


def build_ssh_base_command(config: DeploymentConfig) -> list[str]:
    return [
        "ssh",
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "ControlMaster=auto",
        "-o",
        "ControlPersist=600",
        "-o",
        "ControlPath=~/.ssh/fin_ops_mux_%r_%h_%p",
        f"{config.user}@{config.host}",
    ]


def run_command(command: list[str], *, dry_run: bool, input_bytes: bytes | None = None) -> None:
    if dry_run:
        printable = " ".join(shlex.quote(part) for part in command)
        print(printable)
        return
    subprocess.run(command, check=True, input=input_bytes)


def create_release_archive(config: DeploymentConfig) -> Path:
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


def _tar_filter(tar_info: tarfile.TarInfo) -> tarfile.TarInfo | None:
    name = tar_info.name
    parts = Path(name).parts
    if any(part == "__pycache__" for part in parts):
        return None
    if name.endswith(".pyc") or name.endswith(".pyo") or name.endswith(".DS_Store"):
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
    build_frontend(config)
    archive_path = create_release_archive(config)
    ssh_base = build_ssh_base_command(config)
    remote_script = build_remote_deploy_script(config)
    archive_bytes = archive_path.read_bytes()
    remote_command = ssh_base + ["bash", "-lc", remote_script]
    run_command(remote_command, dry_run=config.dry_run, input_bytes=archive_bytes)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config = build_config(args, root_dir=Path(__file__).resolve().parents[1])
    deploy(config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
