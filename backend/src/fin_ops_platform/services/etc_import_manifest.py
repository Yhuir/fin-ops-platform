from __future__ import annotations

import base64
import gzip
import json
from dataclasses import asdict
from decimal import Decimal

from fin_ops_platform.services.etc_service import (
    EtcArchiveEntry,
    EtcArchiveFileManifest,
    EtcArchiveManifest,
    ParsedEtcXml,
)


def encode_manifest(manifest: EtcArchiveManifest) -> bytes:
    """Persist the already parsed, bounded ZIP manifest as an object, never job JSON."""
    payload = {
        "version": 1,
        "files": [
            {
                "source_name": file.source_name,
                "error": file.error,
                "entries": [
                    {
                        "source_name": entry.source_name,
                        "path": entry.path,
                        "display_path": entry.display_path,
                        "content": base64.b64encode(entry.content).decode("ascii"),
                        "parsed_invoice": asdict(entry.parsed_invoice) if entry.parsed_invoice else None,
                        "parse_error": entry.parse_error,
                    }
                    for entry in file.entries
                ],
            }
            for file in manifest.files
        ],
    }
    return gzip.compress(json.dumps(payload, ensure_ascii=False, default=str).encode(), mtime=0)


def decode_manifest(content: bytes) -> EtcArchiveManifest:
    payload = json.loads(gzip.decompress(content))
    if payload["version"] != 1:
        raise ValueError("ETC prepared manifest version is unsupported; prepare a new preview.")
    files = []
    for file in payload["files"]:
        entries = []
        for entry in file["entries"]:
            parsed = entry["parsed_invoice"]
            if parsed is not None:
                for key in ("amount_without_tax", "tax_amount", "total_amount"):
                    parsed[key] = Decimal(parsed[key])
                parsed = ParsedEtcXml(**parsed)
            entries.append(EtcArchiveEntry(
                source_name=entry["source_name"], path=entry["path"], display_path=entry["display_path"],
                content=base64.b64decode(entry["content"], validate=True), parsed_invoice=parsed,
                parse_error=entry["parse_error"],
            ))
        files.append(EtcArchiveFileManifest(file["source_name"], tuple(entries), file["error"]))
    return EtcArchiveManifest(tuple(files))
