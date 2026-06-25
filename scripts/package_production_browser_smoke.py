from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import tarfile
from typing import Any, Sequence


MANIFEST_NAME = "production-browser-smoke-manifest.json"
DEFAULT_BASE_URL = "https://www.yn-sourcing.com"
APPROVED_BUNDLE_FILES = (
    Path("web/e2e/production-route-shell.spec.ts"),
    Path("web/e2e/fixtures/strictTest.ts"),
    Path("web/playwright.config.ts"),
    Path("web/package.json"),
    Path("web/package-lock.json"),
)


@dataclass(frozen=True)
class BundleConfig:
    root_dir: Path
    output: Path
    release_name: str
    base_url: str


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Package the approved production route-shell browser smoke bundle.",
    )
    parser.add_argument("--output", type=Path, required=True, help="Output .tar.gz path.")
    parser.add_argument("--release-name", default="", help="Expected production release name for the evidence run.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--root-dir", type=Path, default=Path(__file__).resolve().parents[1])
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = BundleConfig(
        root_dir=args.root_dir.resolve(),
        output=args.output,
        release_name=str(args.release_name or ""),
        base_url=str(args.base_url or DEFAULT_BASE_URL),
    )
    manifest = create_production_browser_smoke_bundle(config)
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def create_production_browser_smoke_bundle(config: BundleConfig) -> dict[str, Any]:
    root_dir = config.root_dir
    files = _existing_approved_files(root_dir)
    if not files:
        raise FileNotFoundError("no approved production browser smoke bundle files found")
    _assert_no_forbidden_paths(files)
    manifest = _build_manifest(config, files)
    config.output.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(config.output, "w:gz") as archive:
        for relative_path in files:
            archive.add(root_dir / relative_path, arcname=relative_path.as_posix())
        manifest_bytes = json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
        info = tarfile.TarInfo(MANIFEST_NAME)
        info.size = len(manifest_bytes)
        info.mode = 0o644
        info.mtime = int(datetime.now(UTC).timestamp())
        archive.addfile(info, fileobj=_BytesReader(manifest_bytes))
    return manifest


def _existing_approved_files(root_dir: Path) -> list[Path]:
    return [relative_path for relative_path in APPROVED_BUNDLE_FILES if (root_dir / relative_path).is_file()]


def _assert_no_forbidden_paths(files: Sequence[Path]) -> None:
    forbidden_parts = {"node_modules", "dist", "playwright-report", "test-results"}
    for relative_path in files:
        parts = set(relative_path.parts)
        if parts & forbidden_parts:
            raise ValueError(f"forbidden bundle path: {relative_path.as_posix()}")
        if relative_path.name in {"production-admin-app-health.spec.ts"}:
            raise ValueError(f"admin production smoke is not part of this bundle: {relative_path.as_posix()}")


def _build_manifest(config: BundleConfig, files: Sequence[Path]) -> dict[str, Any]:
    root_dir = config.root_dir
    package_json = json.loads((root_dir / "web/package.json").read_text(encoding="utf-8"))
    return {
        "bundle_version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "git_branch": _git_output(root_dir, "rev-parse", "--abbrev-ref", "HEAD"),
        "git_commit": _git_output(root_dir, "rev-parse", "HEAD"),
        "release_name": config.release_name,
        "base_url": config.base_url,
        "production_spec": "web/e2e/production-route-shell.spec.ts",
        "included_files": [path.as_posix() for path in files],
        "sha256_by_file": {
            path.as_posix(): _sha256(root_dir / path)
            for path in files
        },
        "runtime_contract": {
            "playwright_package": package_json.get("devDependencies", {}).get("@playwright/test", ""),
            "runtime_owner": "dedicated-browser-smoke-runner",
            "browser_download_during_evidence_run": False,
            "package_install_during_evidence_run": False,
        },
        "command_contract": {
            "env": {
                "FIN_OPS_E2E_PRODUCTION_SMOKE": "1",
                "FIN_OPS_E2E_SKIP_WEBSERVER": "1",
                "PLAYWRIGHT_BASE_URL": config.base_url,
                "FIN_OPS_E2E_OA_TOKEN": "<in-memory-only>",
            },
            "argv": [
                "playwright",
                "test",
                "e2e/production-route-shell.spec.ts",
                "--project=chromium",
                "--reporter=list",
            ],
        },
        "artifact_redaction_contract": {
            "screenshots": "forbidden",
            "traces": "forbidden",
            "videos": "forbidden",
            "html_report": "forbidden",
            "page_body_text": "forbidden",
            "response_body_text": "forbidden",
            "raw_console_detail": "forbidden",
            "raw_page_error_detail": "forbidden",
            "full_request_url": "forbidden",
            "tokens_cookies_env_values": "forbidden",
        },
        "normal_app_release_packaging_changed": False,
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_output(root_dir: Path, *args: str) -> str:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=root_dir,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return ""
    return completed.stdout.strip()


class _BytesReader:
    def __init__(self, data: bytes) -> None:
        self._data = data
        self._offset = 0

    def read(self, size: int = -1) -> bytes:
        if size is None or size < 0:
            size = len(self._data) - self._offset
        chunk = self._data[self._offset:self._offset + size]
        self._offset += len(chunk)
        return chunk


if __name__ == "__main__":
    raise SystemExit(main())
