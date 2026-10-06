"""Build, install and audit the App's narrowly patched PyMongo distribution.

No MongoDB connection is made here. The original upstream version remains the
security-database lookup key; only verified backports are classified separately.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "backend/vendor/pymongo"
VERSION = "4.17.0+finops.1"
UPSTREAM_VERSION = "4.17.0"
SOURCE_URL = "https://files.pythonhosted.org/packages/ca/64/50be6fbac9c79fe2e4c17401a467da2d8764d82833d83cec325afe5cab32/pymongo-4.17.0.tar.gz"
SOURCE_SHA256 = "70ffa08ba641468cc068cf46c06b34f01a8ce3489f6411309fcb5ceabe6b2fc0"
FIXED_CVES = frozenset({"CVE-2026-88029", "CVE-2026-96747", "CVE-2026-96748", "CVE-2026-96749"})


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run(*args: str, **kwargs) -> None:
    subprocess.run(list(args), check=True, **kwargs)


def build(wheels: Path) -> Path:
    wheels.mkdir(parents=True, exist_ok=True)
    manifest_path = wheels / "pymongo-build.json"
    if manifest_path.exists():
        return verified_wheel(wheels)
    if list(wheels.glob("pymongo-*.whl")):
        raise ValueError("unverified PyMongo wheel already exists; use a new build directory")
    with tempfile.TemporaryDirectory(prefix="finops-pymongo-build-") as directory:
        work = Path(directory)
        archive = work / "source.tar.gz"
        with urllib.request.urlopen(SOURCE_URL, timeout=60) as response:
            archive.write_bytes(response.read())
        if digest(archive.read_bytes()) != SOURCE_SHA256:
            raise ValueError("PyMongo upstream source digest mismatch")
        with tarfile.open(archive) as source:
            source.extractall(work, filter="data")
        source_root = work / f"pymongo-{UPSTREAM_VERSION}"
        run("patch", "--batch", "--fuzz=0", "-p1", "-i", str(VENDOR / "security.patch"), cwd=source_root)
        # The upstream sdist caches static metadata. Regenerate it from the
        # patched version, otherwise hatch reuses the original public version.
        (source_root / "PKG-INFO").unlink()
        # Pin the build backend as well as the source; do not modify site-packages.
        run(sys.executable, "-m", "venv", str(work / "build-env"))
        python = str(work / "build-env/bin/python")
        run(python, "-m", "pip", "install", "--disable-pip-version-check", "-r", str(VENDOR / "build-requirements.txt"))
        run(python, "-m", "pip", "wheel", "--no-build-isolation", "--no-deps", "--wheel-dir", str(work / "wheels"), str(source_root))
        candidates = list((work / "wheels").glob(f"pymongo-{VERSION}-*.whl"))
        if len(candidates) != 1:
            raise ValueError("expected exactly one patched PyMongo wheel")
        wheel = candidates[0]
        with zipfile.ZipFile(wheel) as package:
            if not any(name.startswith("bson/_cbson") and name.endswith(".so") for name in package.namelist()):
                raise ValueError("patched BSON C extension is missing")
        destination = wheels / wheel.name
        destination.write_bytes(wheel.read_bytes())
        manifest = {
            "version": VERSION,
            "source_sha256": SOURCE_SHA256,
            "patch_sha256": digest((VENDOR / "security.patch").read_bytes()),
            "build_requirements_sha256": digest((VENDOR / "build-requirements.txt").read_bytes()),
            "wheel": wheel.name,
            "wheel_sha256": digest(wheel.read_bytes()),
        }
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    return verified_wheel(wheels)


def verified_wheel(wheels: Path) -> Path:
    manifest = json.loads((wheels / "pymongo-build.json").read_text())
    expected = {
        "version": VERSION,
        "source_sha256": SOURCE_SHA256,
        "patch_sha256": digest((VENDOR / "security.patch").read_bytes()),
        "build_requirements_sha256": digest((VENDOR / "build-requirements.txt").read_bytes()),
    }
    if any(manifest.get(key) != value for key, value in expected.items()):
        raise ValueError("PyMongo build provenance does not match this release")
    name = manifest["wheel"]
    if Path(name).name != name or not name.startswith(f"pymongo-{VERSION}-") or not name.endswith(".whl"):
        raise ValueError("invalid PyMongo wheel name")
    wheel = wheels / name
    if digest(wheel.read_bytes()) != manifest["wheel_sha256"]:
        raise ValueError("PyMongo wheel content changed after build")
    return wheel


def verify_installed(wheels: Path) -> None:
    wheel = verified_wheel(wheels)
    distribution = importlib.metadata.distribution("pymongo")
    if distribution.version != VERSION:
        raise ValueError("installed PyMongo is not the patched release")
    with zipfile.ZipFile(wheel) as package:
        for name in package.namelist():
            if name.startswith(("bson/", "pymongo/", "gridfs/")) and not name.endswith("/"):
                if distribution.locate_file(name).read_bytes() != package.read(name):
                    raise ValueError(f"installed PyMongo differs from verified wheel: {name}")
    import bson
    import pymongo
    if not bson.has_c() or pymongo.version != VERSION:
        raise ValueError("patched driver/C extension was not loaded")


def prepare(requirements: Path, wheels: Path) -> None:
    from packaging.requirements import Requirement
    from packaging.utils import canonicalize_name, parse_wheel_filename

    if f"pymongo=={VERSION}" in requirements.read_text().splitlines():
        build(wheels)
    wheels.mkdir(parents=True, exist_ok=True)
    requested = {canonicalize_name(req.name): req for line in requirements.read_text().splitlines() if line and not line.startswith("#") for req in [Requirement(line)]}
    # Preserve existing transitive versions unless an explicit requirement
    # changes them. A driver release must not incidentally upgrade OCR/numpy.
    constraints = []
    names = {canonicalize_name(d.metadata["Name"]) for d in importlib.metadata.distributions()}
    for name in names:
        version = importlib.metadata.version(name)
        if name in requested and version not in requested[name].specifier:
            continue
        constraints.append(f"{name}=={version}")
    with tempfile.TemporaryDirectory(prefix="finops-existing-dependencies-") as directory:
        constraint = Path(directory) / "constraints.txt"
        constraint.write_text("\n".join(sorted(set(constraints))) + "\n")
        run(sys.executable, "-m", "pip", "download", "--only-binary=:all:", "--find-links", str(wheels), "--dest", str(wheels), "-c", str(constraint), "-r", str(requirements))
    versions = {}
    for wheel in wheels.glob("*.whl"):
        name, version, _, _ = parse_wheel_filename(wheel.name)
        if name in versions and versions[name] != str(version):
            raise ValueError(f"multiple versions in prepared wheel directory: {name}")
        versions[name] = str(version)
    (wheels / "resolved.txt").write_text("\n".join(f"{name}=={version}" for name, version in sorted(versions.items())) + "\n")


def classify_audit(report: dict, *, patched: bool) -> tuple[list[dict], list[dict]]:
    fixed, unresolved = [], []
    dependencies = report.get("dependencies")
    if not isinstance(dependencies, list) or not dependencies:
        raise ValueError("dependency audit returned no dependency inventory")
    for dependency in dependencies:
        if dependency.get("skip_reason") or "version" not in dependency or "vulns" not in dependency:
            raise ValueError("dependency audit skipped an installed dependency")
        for vulnerability in dependency["vulns"]:
            item = {"name": dependency["name"], "version": dependency["version"], **vulnerability}
            identifiers = {vulnerability["id"], *vulnerability.get("aliases", [])}
            if patched and dependency["name"] == "pymongo" and dependency["version"] == UPSTREAM_VERSION and identifiers & FIXED_CVES:
                fixed.append(item)
            else:
                unresolved.append(item)
    return fixed, unresolved


def audit_installed(wheels: Path) -> None:
    # Audit the installed inventory, including transitive dependencies. Looking
    # up the public version prevents an unknown local version from being skipped.
    verify_installed(wheels)
    run(sys.executable, str(VENDOR / "test_security.py"), "-v")
    with tempfile.TemporaryDirectory(prefix="finops-dependency-audit-") as directory:
        requirements = Path(directory) / "installed.txt"
        installed = {d.metadata["Name"]: d.version for d in importlib.metadata.distributions()}
        requirements.write_text("\n".join(f"{name}=={UPSTREAM_VERSION if name.lower() == 'pymongo' else version}" for name, version in sorted(installed.items())) + "\n")
        result = subprocess.run([sys.executable, "-m", "pip_audit", "-r", str(requirements), "--disable-pip", "--no-deps", "--format=json", "--progress-spinner=off"], capture_output=True, text=True)
        if result.returncode not in (0, 1):
            raise RuntimeError(f"dependency audit failed: {result.stderr}")
        report = json.loads(result.stdout)
        from packaging.utils import canonicalize_name
        scanned = {canonicalize_name(item["name"]) for item in report.get("dependencies", [])}
        if scanned != {canonicalize_name(name) for name in installed}:
            raise ValueError("dependency audit inventory differs from the installed environment")
        fixed, unresolved = classify_audit(report, patched=True)
        print(json.dumps({"upstream_audit": report, "verified_backports": fixed, "unresolved": unresolved}, indent=2))
        if unresolved:
            raise RuntimeError(f"{len(unresolved)} unresolved dependency vulnerabilities")


def audit(requirements: Path, wheels: Path) -> None:
    prepare(requirements, wheels)
    # Keep unrelated workstation packages out of the application inventory.
    with tempfile.TemporaryDirectory(prefix="finops-audit-env-") as directory:
        run(sys.executable, "-m", "venv", directory)
        python = str(Path(directory) / "bin/python")
        run(python, "-m", "pip", "install", "--upgrade", "pip", "setuptools")
        run(python, "-m", "pip", "install", "--find-links", str(wheels), "-r", str(wheels / "resolved.txt"), "-r", str(ROOT / "backend/requirements-audit.txt"))
        run(python, str(Path(__file__).resolve()), "audit-installed", "--wheels", str(wheels))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "prepare", "install", "verify", "audit", "audit-installed"))
    parser.add_argument("--requirements", type=Path, default=ROOT / "backend/requirements.txt")
    parser.add_argument("--wheels", type=Path, default=ROOT / ".runtime/python-wheels")
    args = parser.parse_args()
    wheels = args.wheels.resolve()
    if args.command == "build":
        print(build(wheels))
    elif args.command == "prepare":
        prepare(args.requirements.resolve(), wheels)
    elif args.command == "install":
        build(wheels)
        run(sys.executable, "-m", "pip", "install", "--find-links", str(wheels), "-r", str(args.requirements.resolve()))
        verify_installed(wheels)
    elif args.command == "verify":
        verify_installed(wheels)
    elif args.command == "audit-installed":
        audit_installed(wheels)
    else:
        audit(args.requirements.resolve(), wheels)


if __name__ == "__main__":
    main()
