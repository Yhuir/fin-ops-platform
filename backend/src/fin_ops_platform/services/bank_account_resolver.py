from __future__ import annotations

from typing import Callable


class BankAccountResolver:
    _BANK_PREFIXES = {
        "6225": "招商银行",
        "6222": "工商银行",
        "6217": "建设银行",
        "6228": "农业银行",
        "6214": "中国银行",
    }

    def __init__(self, mapping_provider: Callable[[], dict[str, str]] | None = None) -> None:
        self._mapping_provider = mapping_provider

    def resolve_label(
        self,
        account_no: str | None,
        account_name: str | None = None,
        *,
        preferred_bank_name: str | None = None,
        preferred_last4: str | None = None,
    ) -> str:
        if not account_no and not preferred_last4:
            return "未识别账户"

        bank_name = preferred_bank_name or "未识别银行"
        last4 = preferred_last4 or (account_no[-4:] if account_no else "")
        if bank_name == "未识别银行" and last4 and self._mapping_provider is not None:
            mapped_name = self._mapping_provider().get(last4)
            if mapped_name:
                bank_name = mapped_name
        if bank_name == "未识别银行" and account_no:
            for prefix, candidate in self._BANK_PREFIXES.items():
                if account_no.startswith(prefix):
                    bank_name = candidate
                    break

        account_type = "账户"
        if account_name:
            if "基本" in account_name:
                account_type = "基本户"
            elif "一般" in account_name:
                account_type = "一般户"
            elif "专户" in account_name:
                account_type = "专户"

        return f"{bank_name} {account_type} {last4}"
