from __future__ import annotations

from typing import Any

from fin_ops_platform.services.app_settings_service import AppSettingsService


class NoOaBankBatchTagSelectionApplicationService:
    def __init__(
        self,
        *,
        app_settings_service: AppSettingsService,
    ) -> None:
        self._app_settings_service = app_settings_service

    def get_tag_selection_payload(self) -> dict[str, Any]:
        return self._app_settings_service.get_no_oa_bank_batch_tag_selection_payload()

    def update_tag_selection(
        self,
        payload: dict[str, Any],
        *,
        actor_id: str,
    ) -> dict[str, Any]:
        result = self._app_settings_service.update_no_oa_bank_batch_tag_selection(
            payload,
            actor_id=actor_id,
        )
        return result
