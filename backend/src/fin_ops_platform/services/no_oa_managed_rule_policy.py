from __future__ import annotations


NO_OA_MANAGED_LABELS: dict[str, str] = {
    "fee": "手续费",
    "salary": "工资",
    "holiday_bonus": "过节费",
    "bonus": "奖金",
    "tax_payment": "税款",
    "treasury_tax_collection": "代理国库税收收缴",
    "social_security": "社保款",
    "internal_transfer": "内部往来款",
}

NO_OA_MANAGED_BATCH_TYPE_ORDER: tuple[str, ...] = (
    "fee",
    "salary",
    "holiday_bonus",
    "bonus",
    "tax_payment",
    "treasury_tax_collection",
    "social_security",
    "internal_transfer",
)

NO_OA_LEGACY_RELATION_MODE_TO_BATCH_TYPE: dict[str, str] = {
    "salary_personal_auto_match": "salary",
    "internal_transfer_pair": "internal_transfer",
}
NO_OA_LEGACY_RELATION_MODES = frozenset(NO_OA_LEGACY_RELATION_MODE_TO_BATCH_TYPE)
NO_OA_LEGACY_RELATION_MIGRATION_VERSION = "2026-05-no-oa-legacy-relation-v1"
NO_OA_LEGACY_RELATION_MIGRATION_SOURCE = "no_oa_legacy_relation_migration"


def no_oa_batch_type_for_legacy_relation_mode(relation_mode: str) -> str:
    return NO_OA_LEGACY_RELATION_MODE_TO_BATCH_TYPE.get(str(relation_mode or "").strip(), "")


def is_no_oa_managed_old_relation_mode(mode: str | None) -> bool:
    return str(mode or "").strip() in NO_OA_LEGACY_RELATION_MODES


def managed_no_oa_batch_type_for_mode(mode: str | None) -> str | None:
    batch_type = no_oa_batch_type_for_legacy_relation_mode(str(mode or ""))
    return batch_type or None


def workbench_mode_may_auto_close(mode: str | None) -> bool:
    return not is_no_oa_managed_old_relation_mode(mode)
