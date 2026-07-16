from __future__ import annotations

from datetime import datetime


class WorkbenchOaRetentionDateParser:
    """Parses the configured OA retention cutoff date."""

    @staticmethod
    def parse(value: object) -> datetime | None:
        if value in (None, ""):
            return None
        text = str(value).strip()
        if len(text) < 10:
            return None
        try:
            return datetime.strptime(text[:10], "%Y-%m-%d")
        except ValueError:
            return None
