from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID, uuid4


class BankTransactionSplitError(ValueError):
    def __init__(self, code: str, message: str, *, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


def validate_split_parts(
    payload: dict[str, Any],
    *,
    amount: Decimal,
    current_parts: list[dict[str, Any]],
    definitions: list[dict[str, Any]],
) -> list[dict[str, str | int]]:
    """Validate the explicit full replacement; never infer a remainder or a tag."""
    parts = payload.get("parts")
    if not isinstance(parts, list) or len(parts) == 1:
        raise BankTransactionSplitError("invalid_split_parts", "拆分至少需要两个子项；撤销拆分请清空子项。")
    current_ids = {part["id"] for part in current_parts}
    active_codes = {item["code"] for item in definitions if item.get("status") == "active"}
    seen: set[str] = set()
    result: list[dict[str, str | int]] = []
    total = Decimal("0.00")
    for position, part in enumerate(parts):
        if not isinstance(part, dict):
            raise BankTransactionSplitError("invalid_split_parts", "子项格式不正确。")
        category_code = part.get("category_code")
        if not isinstance(category_code, str) or category_code not in active_codes:
            raise BankTransactionSplitError("invalid_split_category", "请选择有效的银行标签。")
        raw_amount = part.get("amount")
        try:
            value = Decimal(raw_amount) if isinstance(raw_amount, str) else Decimal("NaN")
        except InvalidOperation:
            value = Decimal("NaN")
        if not value.is_finite() or value <= 0 or value >= Decimal("1e18") or value != value.quantize(Decimal("0.01")):
            raise BankTransactionSplitError("invalid_split_amount", "子项金额必须为大于零的两位小数金额。")
        item_id = part.get("id")
        if item_id is not None:
            if not isinstance(item_id, str) or item_id not in current_ids or item_id in seen:
                raise BankTransactionSplitError("invalid_split_identity", "子项已变化或不属于当前流水，请重新读取。")
            try:
                UUID(item_id)
            except ValueError as exc:
                raise BankTransactionSplitError("invalid_split_identity", "子项身份不正确。") from exc
        else:
            item_id = str(uuid4())
        seen.add(item_id)
        total += value
        result.append({"id": item_id, "category_code": category_code, "amount": format(value, ".2f"), "position": position})
    if parts and total != amount:
        raise BankTransactionSplitError("split_amount_mismatch", f"子项合计须等于流水金额 {amount:.2f}。")
    if not parts and current_parts and payload.get("category_code") not in active_codes:
        raise BankTransactionSplitError("invalid_split_category", "撤销拆分时请选择整笔流水标签。")
    return result


class BankTransactionSplitService:
    def __init__(self, *, repository: Any, relation_service: Any) -> None:
        self._repository = repository
        self._relation_service = relation_service

    def read(self, transaction_id: str) -> dict[str, Any]:
        with self._repository.transaction(read_only=True) as transaction:
            return self._repository.load(transaction, transaction_id, for_update=False)

    def read_many(self, payload: dict[str, Any]) -> dict[str, Any]:
        ids = payload.get("transaction_ids")
        if not isinstance(ids, list) or not ids or any(not isinstance(value, str) or not value.strip() for value in ids):
            raise BankTransactionSplitError("invalid_transaction_ids", "请选择有效的银行流水。")
        with self._repository.transaction(read_only=True) as transaction:
            return {"rows": self._repository.load_many(transaction, ids)}

    def save(self, transaction_id: str, payload: dict[str, Any], *, actor_id: str) -> dict[str, Any]:
        version = payload.get("version")
        if type(version) is not int or version < 0:
            raise BankTransactionSplitError("invalid_split_version", "缺少有效的流水编辑版本。")
        if not actor_id:
            raise BankTransactionSplitError("permission_denied", "请登录后再保存。", status=403)
        with self._repository.transaction(read_only=False) as transaction:
            before = self._repository.load(transaction, transaction_id, for_update=True)
            if version != before["version"]:
                raise BankTransactionSplitError("split_version_conflict", "流水拆分已被修改，请重新读取后再保存。", status=409)
            if Decimal(before["written_off_amount"]) != 0:
                raise BankTransactionSplitError("bank_transaction_already_written_off", "请先撤销该流水的核销，再编辑拆分。", status=409)
            parts = validate_split_parts(
                payload,
                amount=Decimal(before["amount"]),
                current_parts=before["parts"],
                definitions=before["tag_definitions"],
            )
            old_values = [(part["id"], part["category_code"], part["amount"]) for part in before["parts"]]
            new_values = [(part["id"], part["category_code"], part["amount"]) for part in parts]
            if old_values == new_values:
                return {**before, "changed": False, "affected_months": []}
            after = self._repository.persist(
                transaction, before=before, parts=parts,
                category_code=payload.get("category_code"), actor_id=actor_id,
            )
            effects = self._relation_service.apply(transaction, before=before, after=after, actor_id=actor_id)
            self._repository.audit(transaction, before=before, after=after, actor_id=actor_id)
        self._relation_service.after_commit(effects)
        return {**after, "changed": True}
