from __future__ import annotations

from datetime import datetime
import os
import re
from typing import Any, Callable

from fin_ops_platform.services.tax_offset_runtime_service import TaxOffsetRuntimeService


MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


class TaxOffsetCacheWarmupExecutor:
    def __init__(
        self,
        *,
        runtime_service: TaxOffsetRuntimeService,
        background_job_service: Any,
        month_payload_loader: Callable[[str], dict[str, object]],
        enabled_provider: Callable[[], bool] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._runtime_service = runtime_service
        self._background_job_service = background_job_service
        self._month_payload_loader = month_payload_loader
        self._enabled_provider = enabled_provider or self.env_enabled
        self._clock = clock or datetime.now

    def schedule(self, months: list[str], *, reason: str) -> None:
        if not self._enabled_provider():
            return
        deduped_months = self._deduped_months(months)
        if not deduped_months:
            return
        affected_scope_keys = [self._runtime_service.scope_key(month) for month in deduped_months]
        idempotency_key = f"tax_offset_cache_warmup:{reason}:{','.join(deduped_months)}"
        job, created = self._background_job_service.create_or_get_idempotent_job_with_created(
            job_type="tax_offset_cache_warmup",
            label="预热税金抵扣缓存",
            owner_user_id="system",
            idempotency_key=idempotency_key,
            visibility="system",
            phase="queued",
            current=0,
            total=len(affected_scope_keys),
            message="税金抵扣缓存预热任务已创建。",
            result_summary={"warmed": 0, "failed": 0},
            source={"reason": reason},
            affected_scopes=affected_scope_keys,
            affected_months=deduped_months,
        )
        if not created:
            return
        self._background_job_service.run_job(
            job,
            lambda running_job: self.run_job(
                running_job,
                months=deduped_months,
            ),
        )

    def run_job(
        self,
        running_job: Any,
        *,
        months: list[str],
    ) -> dict[str, object]:
        warmed_scope_keys: list[str] = []
        failed_scope_keys: list[str] = []
        total = len(list(months or []))
        for index, month in enumerate(list(months or []), start=1):
            scope_key = self._runtime_service.scope_key(month)
            self._background_job_service.update_progress(
                running_job.job_id,
                phase="build_tax_offset_cache",
                message=f"正在预热税金抵扣缓存 {index}/{max(total, 1)}。",
                current=index - 1,
                total=total,
                result_summary={"warmed": len(warmed_scope_keys), "failed": len(failed_scope_keys)},
            )
            try:
                payload = self._load_month_payload(month)
            except Exception:
                failed_scope_keys.append(scope_key)
                continue
            warmed_scope_keys.append(scope_key)

        result_summary = {
            "warmed": len(warmed_scope_keys),
            "failed": len(failed_scope_keys),
        }
        message = "税金抵扣缓存预热完成。" if not failed_scope_keys else "税金抵扣缓存预热部分完成。"
        self._background_job_service.succeed_job(
            running_job.job_id,
            message,
            result_summary=result_summary,
            status="partial_success" if failed_scope_keys else "succeeded",
        )
        return result_summary

    @staticmethod
    def env_enabled() -> bool:
        return os.getenv("FIN_OPS_TAX_OFFSET_CACHE_WARMUP_ENABLED", "0").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    @staticmethod
    def _deduped_months(months: list[str]) -> list[str]:
        return sorted(
            {
                str(month).strip()
                for month in list(months or [])
                if MONTH_RE.match(str(month).strip())
            },
            reverse=True,
        )

    def _load_month_payload(self, month: str) -> dict[str, object]:
        payload = self._month_payload_loader(month)
        if not isinstance(payload, dict):
            raise RuntimeError("Tax offset month payload loader must return a dict.")
        return dict(payload)
