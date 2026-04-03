from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from itertools import count

from fin_ops_platform.domain.enums import (
    LedgerStatus,
    LedgerType,
    ReminderStatus,
)
from fin_ops_platform.domain.models import (
    ExceptionHandlingRecord,
    FollowUpLedger,
    Invoice,
    Reminder,
    ReconciliationCase,
)
from fin_ops_platform.services.audit import AuditTrailService
from fin_ops_platform.services.imports import ImportNormalizationService


ZERO = Decimal("0.00")


class LedgerReminderService:
    def __init__(
        self,
        import_service: ImportNormalizationService,
        audit_service: AuditTrailService,
    ) -> None:
        self._import_service = import_service
        self._audit_service = audit_service
        self._ledger_sequence = count(1)
        self._reminder_sequence = count(1)
        self._ledgers: dict[str, FollowUpLedger] = {}
        self._ledger_index: dict[tuple[str, str], str] = {}
        self._reminders: dict[str, Reminder] = {}
        self._reminder_index: dict[tuple[str, str, str], str] = {}

    def sync_from_case(
        self,
        case: ReconciliationCase,
        *,
        exception_record: ExceptionHandlingRecord | None = None,
    ) -> list[FollowUpLedger]:
        specs = self._build_specs(case, exception_record=exception_record)
        ledgers: list[FollowUpLedger] = []
        for spec in specs:
            if spec["open_amount"] <= ZERO:
                continue
            ledgers.append(self._upsert_ledger(case, **spec))
        return ledgers

    def list_ledgers(
        self,
        *,
        view: str = "all",
        as_of: str | None = None,
        status: LedgerStatus | str | None = None,
    ) -> list[FollowUpLedger]:
        ledgers = list(self._ledgers.values())
        if status is not None:
            target_status = LedgerStatus(status)
            ledgers = [ledger for ledger in ledgers if ledger.status == target_status]
        if view == "all":
            return ledgers
        as_of_date = self._parse_date(as_of) if as_of else date.today()
        open_ledgers = [
            ledger for ledger in ledgers if ledger.status not in {LedgerStatus.RESOLVED, LedgerStatus.CANCELLED}
        ]
        if view == "overdue":
            return [ledger for ledger in open_ledgers if self._parse_date(ledger.expected_date) < as_of_date]
        if view == "due":
            horizon = as_of_date + timedelta(days=7)
            return [
                ledger
                for ledger in open_ledgers
                if as_of_date <= self._parse_date(ledger.expected_date) <= horizon
            ]
        return open_ledgers

    def get_ledger(self, ledger_id: str) -> FollowUpLedger:
        return self._ledgers[ledger_id]

    def update_ledger(
        self,
        ledger_id: str,
        *,
        actor_id: str,
        status: LedgerStatus | str | None = None,
        expected_date: str | None = None,
        note: str | None = None,
    ) -> FollowUpLedger:
        ledger = self._ledgers[ledger_id]
        previous_status = ledger.status
        previous_note = ledger.latest_note
        if status is not None:
            ledger.status = LedgerStatus(status)
        if expected_date is not None:
            ledger.expected_date = expected_date
        if note is not None:
            ledger.latest_note = note
        self._audit_service.record_action(
            actor_id=actor_id,
            action="follow_up_ledger_status_updated",
            entity_type="follow_up_ledger",
            entity_id=ledger.id,
            metadata={
                "before_status": previous_status.value,
                "after_status": ledger.status.value,
                "before_note": previous_note,
                "after_note": ledger.latest_note,
                "expected_date": ledger.expected_date,
            },
        )
        return ledger

    def schedule_reminders(
        self,
        *,
        as_of: str,
        days_ahead: int = 7,
        channel: str = "in_app",
    ) -> list[Reminder]:
        as_of_date = self._parse_date(as_of)
        horizon = as_of_date + timedelta(days=days_ahead)
        created: list[Reminder] = []
        for ledger in self.list_ledgers(view="all"):
            if ledger.status in {LedgerStatus.RESOLVED, LedgerStatus.CANCELLED}:
                continue
            expected_date = self._parse_date(ledger.expected_date)
            if expected_date > horizon:
                continue
            remind_on = max(as_of_date, expected_date - timedelta(days=1)).isoformat()
            existing = self._existing_active_reminder(ledger.id, channel)
            if existing is not None:
                continue
            key = (ledger.id, remind_on, channel)
            reminder = Reminder(
                id=f"rem_{next(self._reminder_sequence):04d}",
                ledger_id=ledger.id,
                remind_at=remind_on,
                channel=channel,
                status=ReminderStatus.PENDING,
            )
            self._reminders[reminder.id] = reminder
            self._reminder_index[key] = reminder.id
            created.append(reminder)
        return created

    def list_reminders(
        self,
        *,
        as_of: str | None = None,
        status: ReminderStatus | str | None = None,
    ) -> list[Reminder]:
        reminders = list(self._reminders.values())
        if status is not None:
            target_status = ReminderStatus(status)
            reminders = [reminder for reminder in reminders if reminder.status == target_status]
        if as_of is not None:
            as_of_date = self._parse_date(as_of)
            reminders = [reminder for reminder in reminders if self._parse_date(reminder.remind_at) <= as_of_date]
        return reminders

    def run_reminders(self, *, as_of: str, days_ahead: int = 7) -> list[Reminder]:
        self.schedule_reminders(as_of=as_of, days_ahead=days_ahead)
        due = self.list_reminders(as_of=as_of, status=ReminderStatus.PENDING)
        now = datetime.now(UTC)
        for reminder in due:
            reminder.status = ReminderStatus.SENT
            reminder.sent_result = f"simulated:{reminder.ledger_id}"
            reminder.sent_at = now
            ledger = self._ledgers[reminder.ledger_id]
            ledger.last_reminded_at = now
        return due

    def _build_specs(
        self,
        case: ReconciliationCase,
        *,
        exception_record: ExceptionHandlingRecord | None,
    ) -> list[dict[str, object]]:
        if exception_record is not None:
            ledger_type = self._map_exception_code(exception_record.exception_code)
            open_amount = self._case_open_amount(case)
            return [
                {
                    "ledger_type": ledger_type,
                    "open_amount": open_amount,
                    "expected_date": self._derive_expected_date(case, ledger_type),
                    "latest_note": exception_record.note or exception_record.exception_title,
                }
            ]

        invoices = self._case_invoices(case)
        transactions = self._case_transactions(case)
        invoice_open_amount = sum((invoice.outstanding_amount for invoice in invoices), start=ZERO)
        transaction_open_amount = sum((transaction.outstanding_amount for transaction in transactions), start=ZERO)
        specs: list[dict[str, object]] = []
        if case.biz_side == "receivable":
            if invoice_open_amount > ZERO:
                specs.append(
                    {
                        "ledger_type": LedgerType.PAYMENT_COLLECTION,
                        "open_amount": invoice_open_amount,
                        "expected_date": self._derive_expected_date(case, LedgerType.PAYMENT_COLLECTION),
                        "latest_note": case.remark or "部分收款待继续催收",
                    }
                )
            if transaction_open_amount > ZERO:
                specs.append(
                    {
                        "ledger_type": LedgerType.ADVANCE_RECEIPT,
                        "open_amount": transaction_open_amount,
                        "expected_date": self._derive_expected_date(case, LedgerType.ADVANCE_RECEIPT),
                        "latest_note": case.remark or "收款超票面金额，待后续冲抵或退款",
                    }
                )
        else:
            if invoice_open_amount > ZERO:
                specs.append(
                    {
                        "ledger_type": LedgerType.PAYMENT_REMINDER,
                        "open_amount": invoice_open_amount,
                        "expected_date": self._derive_expected_date(case, LedgerType.PAYMENT_REMINDER),
                        "latest_note": case.remark or "发票已到但仍待付款",
                    }
                )
            if transaction_open_amount > ZERO:
                specs.append(
                    {
                        "ledger_type": LedgerType.INVOICE_COLLECTION if invoices else LedgerType.PREPAYMENT,
                        "open_amount": transaction_open_amount,
                        "expected_date": self._derive_expected_date(
                            case,
                            LedgerType.INVOICE_COLLECTION if invoices else LedgerType.PREPAYMENT,
                        ),
                        "latest_note": case.remark or "付款金额超出当前票面，待追票或转预付",
                    }
                )
        return specs

    def _upsert_ledger(
        self,
        case: ReconciliationCase,
        *,
        ledger_type: LedgerType,
        open_amount: Decimal,
        expected_date: str,
        latest_note: str | None,
    ) -> FollowUpLedger:
        key = (case.id, ledger_type.value)
        existing_id = self._ledger_index.get(key)
        if existing_id is not None:
            ledger = self._ledgers[existing_id]
            before_amount = ledger.open_amount
            ledger.open_amount = open_amount
            ledger.expected_date = expected_date
            ledger.latest_note = latest_note
            ledger.status = LedgerStatus.RESOLVED if open_amount <= ZERO else ledger.status
            self._audit_service.record_action(
                actor_id=case.created_by or "system",
                action="follow_up_ledger_updated",
                entity_type="follow_up_ledger",
                entity_id=ledger.id,
                before_amount=before_amount,
                after_amount=ledger.open_amount,
                metadata={"ledger_type": ledger.ledger_type.value, "source_case_id": case.id},
            )
            return ledger

        ledger = FollowUpLedger(
            id=f"ledger_{next(self._ledger_sequence):04d}",
            ledger_type=ledger_type,
            source_object_type="reconciliation_case",
            source_object_id=case.id,
            counterparty_id=case.counterparty_id,
            open_amount=open_amount,
            expected_date=expected_date,
            owner_id=case.created_by or "system",
            source_case_id=case.id,
            project_id=case.project_id,
            latest_note=latest_note,
            status=LedgerStatus.OPEN,
        )
        self._ledgers[ledger.id] = ledger
        self._ledger_index[key] = ledger.id
        self._audit_service.record_action(
            actor_id=case.created_by or "system",
            action="follow_up_ledger_created",
            entity_type="follow_up_ledger",
            entity_id=ledger.id,
            before_amount=ZERO,
            after_amount=open_amount,
            metadata={"ledger_type": ledger_type.value, "source_case_id": case.id},
        )
        return ledger

    def _case_invoices(self, case: ReconciliationCase) -> list[Invoice]:
        invoice_ids = [line.object_id for line in case.lines if line.object_type == "invoice"]
        return [self._import_service.get_invoice(invoice_id) for invoice_id in invoice_ids]

    def _case_transactions(self, case: ReconciliationCase):
        txn_ids = [line.object_id for line in case.lines if line.object_type == "bank_txn"]
        return [self._import_service.get_transaction(txn_id) for txn_id in txn_ids]

    def _case_open_amount(self, case: ReconciliationCase) -> Decimal:
        invoice_amount = sum((invoice.outstanding_amount for invoice in self._case_invoices(case)), start=ZERO)
        transaction_amount = sum((txn.outstanding_amount for txn in self._case_transactions(case)), start=ZERO)
        open_amount = invoice_amount + transaction_amount
        return open_amount if open_amount > ZERO else case.total_amount

    def _derive_expected_date(self, case: ReconciliationCase, ledger_type: LedgerType) -> str:
        base_date = self._case_base_date(case)
        offset_days = {
            LedgerType.PAYMENT_COLLECTION: 7,
            LedgerType.INVOICE_COLLECTION: 5,
            LedgerType.REFUND: 3,
            LedgerType.ADVANCE_RECEIPT: 5,
            LedgerType.PREPAYMENT: 5,
            LedgerType.OUTPUT_INVOICE_ISSUE: 3,
            LedgerType.PAYMENT_REMINDER: 7,
            LedgerType.EXTERNAL_RECEIVABLE_PAYABLE: 7,
            LedgerType.NON_TAX_INCOME: 2,
        }[ledger_type]
        return (base_date + timedelta(days=offset_days)).isoformat()

    def _case_base_date(self, case: ReconciliationCase) -> date:
        invoices = self._case_invoices(case)
        if invoices and invoices[0].invoice_date:
            return self._parse_date(invoices[0].invoice_date)
        transactions = self._case_transactions(case)
        if transactions and transactions[0].txn_date:
            return self._parse_date(transactions[0].txn_date)
        return case.created_at.date()

    @staticmethod
    def _map_exception_code(exception_code: str) -> LedgerType:
        if exception_code == "SO-A":
            return LedgerType.PAYMENT_COLLECTION
        if exception_code == "SO-B":
            return LedgerType.OUTPUT_INVOICE_ISSUE
        if exception_code in {"SO-C", "SO-D"}:
            return LedgerType.ADVANCE_RECEIPT
        if exception_code in {"SO-E", "SO-F", "SO-H", "PI-E", "PI-F"}:
            return LedgerType.EXTERNAL_RECEIVABLE_PAYABLE
        if exception_code == "SO-G":
            return LedgerType.NON_TAX_INCOME
        if exception_code in {"PI-A", "PI-B", "PI-D"}:
            return LedgerType.INVOICE_COLLECTION
        if exception_code == "PI-C":
            return LedgerType.REFUND
        if exception_code in {"PI-G", "PI-H"}:
            return LedgerType.PAYMENT_REMINDER
        return LedgerType.EXTERNAL_RECEIVABLE_PAYABLE

    @staticmethod
    def _parse_date(value: str) -> date:
        return datetime.strptime(value, "%Y-%m-%d").date()

    def _existing_active_reminder(self, ledger_id: str, channel: str) -> Reminder | None:
        for reminder in self._reminders.values():
            if reminder.ledger_id == ledger_id and reminder.channel == channel and reminder.status != ReminderStatus.CANCELLED:
                return reminder
        return None
