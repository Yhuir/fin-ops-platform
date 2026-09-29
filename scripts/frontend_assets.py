"""Publish immutable Vite assets before atomically switching the HTML entry.

The private inventory lives beside dist, independently of backend release pruning.
The deploy-control activation lock owns publish, verify and post-checkpoint cleanup.
"""
from __future__ import annotations

import argparse
import json
import os
import tempfile
import time
from pathlib import Path, PurePosixPath

RETENTION_SECONDS = 7 * 24 * 60 * 60


def atomic_write(path: Path, data: bytes, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".frontend-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fchmod(stream.fileno(), mode)
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def asset_path(dist: Path, name: str) -> Path:
    relative = PurePosixPath(name)
    if relative.is_absolute() or len(relative.parts) < 2 or relative.parts[0] != "assets" or ".." in relative.parts:
        raise ValueError(f"invalid managed asset path: {name}")
    path = dist / name
    if dist.is_symlink() or any((dist / Path(*relative.parts[:i])).is_symlink() for i in range(1, len(relative.parts) + 1)):
        raise ValueError(f"symlink is not a managed asset: {name}")
    return path


def build_inventory(dist: Path) -> dict:
    files = []
    for path in sorted(dist.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"symlink in frontend build: {path.name}")
        if not path.is_file() or path.name == "index.html" and path.parent == dist:
            continue
        name = path.relative_to(dist).as_posix()
        asset_path(dist, name)
        files.append(name)
    if not files:
        raise ValueError("frontend build has no assets")
    return {"index": (dist / "index.html").read_text(), "files": files, "retired_at": None}


class FrontendAssets:
    def __init__(self, dist: Path):
        self.dist = dist
        self.inventory_path = dist.parent / ".frontend-assets.json"

    def load(self) -> dict:
        return json.loads(self.inventory_path.read_text())

    def save(self, state: dict) -> None:
        atomic_write(self.inventory_path, (json.dumps(state, sort_keys=True) + "\n").encode(), 0o600)

    def copy_assets(self, source: Path, entry: dict) -> None:
        for name in entry["files"]:
            data = asset_path(source, name).read_bytes()
            target = asset_path(self.dist, name)
            if target.exists():
                if target.read_bytes() != data:
                    raise ValueError(f"immutable asset content conflict: {name}")
            else:
                atomic_write(target, data)

    def bootstrap(self, release_root: Path, now: float) -> dict:
        """Recover only intact, recent release builds; never scan backup directories."""
        current = (self.dist / "index.html").read_text()
        versions = {}
        for source in sorted(release_root.glob("*/src/web/dist")):
            index = source / "index.html"
            if not index.is_file():
                continue
            if index.stat().st_mtime < now - RETENTION_SECONDS and index.read_text() != current:
                continue
            entry = build_inventory(source)
            entry["retired_at"] = now
            versions[source.parents[2].name] = entry
        matches = [name for name, entry in versions.items() if entry["index"] == current]
        if not matches:
            raise ValueError("published HTML has no intact release build; bootstrap refused")
        # Register before copying: an interrupted copy remains managed and is resumed on publish.
        state = {"versions": versions, "previous": matches[-1]}
        self.save(state)
        for name, entry in versions.items():
            self.copy_assets(release_root / name / "src/web/dist", entry)
        return state

    def publish(self, source: Path, release_root: Path, now: float) -> None:
        candidate = build_inventory(source)
        name = source.parents[2].name
        state = self.load() if self.inventory_path.exists() else self.bootstrap(release_root, now)
        current = (self.dist / "index.html").read_text()
        matching = [key for key, value in state["versions"].items() if value["index"] == current]
        if not matching:
            raise ValueError("published HTML is outside managed inventory")
        # A same-build backend release does not retire the frontend that remains in use.
        for entry in state["versions"].values():
            if entry["index"] == current or entry["retired_at"] is None:
                entry["retired_at"] = now
        previous = matching[-1]
        if current != candidate["index"]:
            state["previous"] = previous
        state["versions"][name] = candidate
        self.save(state)
        # Resume bootstrap copies if the first migration was interrupted.
        for key, entry in state["versions"].items():
            origin = release_root / key / "src/web/dist"
            missing = [item for item in entry["files"] if not asset_path(self.dist, item).is_file()]
            supported = (entry["index"] == current or key == state["previous"]
                         or entry["retired_at"] is None or entry["retired_at"] >= now - RETENTION_SECONDS)
            if missing and supported:
                self.copy_assets(origin, {**entry, "files": missing})
        self.copy_assets(source, candidate)
        atomic_write(self.dist / "index.html", candidate["index"].encode())

    def verify(self, source: Path) -> None:
        expected = build_inventory(source)
        if (self.dist / "index.html").read_text() != expected["index"]:
            raise ValueError("published HTML differs from target release")
        for name in expected["files"]:
            if asset_path(self.dist, name).read_bytes() != asset_path(source, name).read_bytes():
                raise ValueError(f"published asset differs from target release: {name}")
        managed = set(expected["files"])
        if self.inventory_path.exists():
            state = self.load()
            managed.update(name for entry in state["versions"].values() for name in entry["files"])
        actual = set(build_inventory(self.dist)["files"])
        if actual - managed:
            raise ValueError("published directory contains unmanaged assets")

    def cleanup(self, now: float) -> None:
        state = self.load()
        current = (self.dist / "index.html").read_text()
        versions = state["versions"]
        if not any(entry["index"] == current for entry in versions.values()):
            raise ValueError("published HTML is outside managed inventory")
        expired = {name for name, entry in versions.items()
                   if name != state["previous"] and entry["index"] != current
                   and entry["retired_at"] is not None and entry["retired_at"] < now - RETENTION_SECONDS}
        retained = {file for name, entry in versions.items() if name not in expired for file in entry["files"]}
        removed = {file for name in expired for file in versions[name]["files"]} - retained
        for name in sorted(removed):
            asset_path(self.dist, name).unlink(missing_ok=True)
        for name in expired:
            del versions[name]
        self.save(state)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("publish", "verify", "cleanup"))
    parser.add_argument("--dist", required=True, type=Path)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--release-root", type=Path)
    args = parser.parse_args()
    publisher = FrontendAssets(args.dist)
    if args.action == "publish":
        if args.source is None or args.release_root is None:
            parser.error("publish requires --source and --release-root")
        publisher.publish(args.source, args.release_root, time.time())
    elif args.action == "verify":
        if args.source is None:
            parser.error("verify requires --source")
        publisher.verify(args.source)
    else:
        publisher.cleanup(time.time())


if __name__ == "__main__":
    main()
