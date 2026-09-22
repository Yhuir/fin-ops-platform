from __future__ import annotations

from dataclasses import asdict
from hashlib import sha256
from typing import Any
from uuid import uuid4

from fin_ops_platform.services.import_job_queue import ImportJob, ImportJobIdempotencyConflict

IMPORT_JOB_PREFIX = "import:"
IMPORT_JOB_TYPES = {
    "file_import.confirm": ("file_import", "文件导入", "/operations/app-health"),
    "etc_invoice_import.confirm": ("etc_invoice_import", "ETC发票导入", "/imports/etc-invoices"),
    "tax_certified_import.confirm": ("tax_certified_import", "已认证发票导入", "/tax-offset"),
    "oa_manual_import.create": ("oa_manual_import", "OA手动导入", "/settings"),
}


IMPORT_DOMAIN_ROUTES = {
    "imports_bank_transactions": "/imports/bank-transactions",
    "imports_invoices": "/imports/invoices",
    "imports_etc_invoices": "/imports/etc-invoices",
    "tax_offset": "/tax-offset",
    "settings": "/settings",
}
LEGACY_IMPORT_JOB_TYPES = frozenset({"file_import", "etc_invoice_import", "tax_certified_import", "oa_manual_import"})


def assert_import_not_disposed(job: ImportJob) -> None:
    if "disposition" in job.result_payload:
        raise ImportJobIdempotencyConflict("该任务已结束处理；如需导入，请发起新的导入。")


def requires_repreview(job: ImportJob) -> bool:
    # Historical review rejection is an explicit, known contract; never auto-confirm it.
    return job.status == "needs_review" or (
        job.status == "failed" and job.import_type == "file_import.confirm" and job.stage == "commit"
        and (job.last_error or "").startswith("selected files require review before confirmation: ")
    )


def upload_request_descriptor(uploads: list[Any]) -> list[dict[str, Any]]:
    """Identify request bytes/options; never used for business item deduplication."""
    descriptors = []
    for upload in uploads:
        values = asdict(upload)
        content = values.pop("content")
        descriptors.append({**values, "content_sha256": sha256(content).hexdigest()})
    return descriptors


def import_job_payload(job: ImportJob) -> dict[str, Any]:
    """Project the durable import job into the existing global progress contract."""
    job_type, label, route = IMPORT_JOB_TYPES[job.import_type]
    status = {
        "pending": "queued", "processing": "running", "canceled": "cancelled",
        "awaiting_confirmation": "awaiting_confirmation", "needs_review": "needs_review",
        "succeeded": "succeeded", "failed": "failed",
    }[job.status]
    result = {key: value for key, value in job.result_payload.items() if key not in {"preview", "session"}}
    if status == "succeeded" and result.get("outcome") == "partial_success":
        status = "partial_success"
    source = {key: value for key, value in job.payload.items() if key not in {"upload_manifest", "command_actor"}}
    source["session_id"] = job.import_session_id
    domains = list(job.affected_domains) if job.affected_domains is not None else [
        key for key, value in IMPORT_DOMAIN_ROUTES.items() if value == source.get("route", route)
    ]
    if job.import_type == "etc_invoice_import.confirm":
        domains = ["imports_etc_invoices", "etc_tickets"]
    source["affected_domains"] = domains
    source["route"] = IMPORT_DOMAIN_ROUTES[domains[0]] if len(domains) == 1 and domains[0] in IMPORT_DOMAIN_ROUTES else route
    source["import_job_id"] = job.import_job_id
    total = int(source.get("total") or len(source.get("selected_file_ids") or []))
    message = {
        "queued": "已受理，等待处理。", "running": "正在解析文件。" if job.stage == "prepare" else "正在导入。",
        "needs_review": "预览需要复核，请修正后重新预览。",
        "awaiting_confirmation": "预览已就绪，请查看并确认。", "failed": "导入失败，请查看原因后重试。",
        "succeeded": "检查完成，无需导入。" if result.get("outcome") == "no_changes" else "导入完成。",
        "partial_success": f"部分导入完成，{len(result.get('failed') or [])} 项失败，请查看明细后重新选择失败项。",
        "cancelled": "导入已取消。",
    }[status]
    if requires_repreview(job):
        message = "预览需要复核，请修正后重新预览并确认。"
    disposed = "disposition" in job.result_payload
    if disposed:
        message = "任务已结束处理，原执行结果保留。"
    return {
        "job_id": IMPORT_JOB_PREFIX + job.import_job_id,
        "import_job_id": job.import_job_id,
        "type": job_type, "label": source.get("label") or label,
        "short_label": message, "status": status, "phase": job.stage,
        "version": job.version, "current": total if status in {"succeeded", "partial_success"} else 0,
        "total": total, "percent": 100 if status in {"succeeded", "partial_success"} else 0,
        "message": message, "result_summary": result, "source": source,
        "affected_domains": source.get("affected_domains", []), "route": source["route"],
        "retryable": not disposed and status in {"failed", "needs_review"}, "retry_mode": "reprepare" if requires_repreview(job) else "same_intent",
        "acknowledgeable": not disposed and status in {"failed", "succeeded", "partial_success", "cancelled"}
            and not (job.import_type in SHARED_IMPORT_TYPES and status == "failed"),
        "attention": not disposed and status in {"failed", "partial_success", "awaiting_confirmation", "needs_review"},
        "error": job.last_error,
        "created_at": str(job.created_at or ""), "updated_at": str(job.updated_at or ""),
        "finished_at": str(job.finished_at) if job.finished_at else None,
    }


SHARED_IMPORT_TYPES = frozenset({"file_import.confirm", "etc_invoice_import.confirm"})


def assert_import_session_access(*, session_id: str, creator: str, actor: str, job: ImportJob | None) -> None:
    """A registered shared task grants session access; unregistered drafts remain private."""
    if job is not None:
        if (job.import_type not in SHARED_IMPORT_TYPES or job.import_session_id != session_id
                or job.created_by != creator):
            raise PermissionError("Import task and session provenance do not match.")
    elif creator != actor:
        raise PermissionError("Import draft belongs to another user.")


class ImportWorkflowService:
    """Own import commands; domain services own previews and financial writes."""

    def __init__(self, repository: Any, *, command_actor: dict[str, str] | None = None) -> None:
        self.repository = repository
        self.command_actor = command_actor

    def command_context(self, actor: str) -> dict[str, Any]:
        if self.command_actor is not None and self.command_actor["actor_account"] != actor:
            raise ValueError("Command actor does not match the authenticated account.")
        return {"actor_account": actor, **({"command_actor": self.command_actor} if self.command_actor is not None else {})}

    def register_files(self, *, file_service: Any, store: Any, owner: str,
                       uploads: list[Any], request_id: str | None = None) -> tuple[Any, ImportJob]:
        request_key = f"file_import.upload:{owner}:{request_id or uuid4()}"
        descriptor = upload_request_descriptor(uploads)
        existing = self.repository.get_by_idempotency_key(request_key, created_by=owner)
        if existing is not None:
            if existing.payload.get("upload_manifest") != descriptor:
                raise ImportJobIdempotencyConflict("同一上传请求的文件或选项不同，请重新发起上传。")
            return None, existing
        session = file_service.register_uploads(imported_by=owner, uploads=uploads)
        payload = {
            "session_id": session.id, "owner_user_id": owner, **self.command_context(owner), "total": len(session.files),
            "upload_manifest": descriptor,
            "selected_file_ids": [item.id for item in session.files],
            "route": "/imports/bank-transactions" if all(
                str(getattr(upload, "batch_type_override", "")).endswith("bank_transaction") for upload in uploads
            ) else "/imports/invoices",
        }
        registered: list[ImportJob] = []

        def register_job(transaction: Any) -> None:
            registered.append(self.repository.create_or_get_job(
                import_type="file_import.confirm", import_session_id=session.id,
                idempotency_key=request_key, payload=payload, created_by=owner,
                stage="prepare", transaction=transaction,
            ))

        try:
            store.save_import_registration(file_service.preview_session_persistence_payload(session.id), register_job=register_job)
        except ImportJobIdempotencyConflict:
            store.delete_unregistered_import_uploads(session.id, session.files)
            # A concurrent identical upload may have won after the initial read.
            # Its transaction is committed; this transaction has rolled back.
            existing = self.repository.get_by_idempotency_key(request_key, created_by=owner)
            if existing is None or existing.payload.get("upload_manifest") != descriptor:
                raise
            return None, existing
        except Exception:
            store.delete_unregistered_import_uploads(session.id, session.files)
            raise
        return session, registered[0]

    def revise_files(self, *, file_service: Any, store: Any, session_id: str, owner: str,
                     selected_file_ids: list[str], overrides: dict[str, Any] | None = None) -> ImportJob:
        self.assert_file_session_access(file_service, session_id=session_id, actor=owner)
        job = self.session_job(session_id, owner, "file_import.confirm")
        if job is not None:
            assert_import_not_disposed(job)
        if job is not None and job.status not in {"awaiting_confirmation", "needs_review", "failed"}:
            raise ImportJobIdempotencyConflict("当前导入任务不能修改预览，请等待任务结束。")
        # Work on a session copy; failed persistence must not change this process's draft.
        before = file_service.draft_checkpoint(session_id)
        try:
            session = file_service.register_reprepare(session_id=session_id, selected_file_ids=selected_file_ids, overrides=overrides)
            payload = {"session_id": session_id, "owner_user_id": session.imported_by, **self.command_context(owner), "selected_file_ids": selected_file_ids,
                       "total": len(selected_file_ids), "route": (job.payload.get("route") if job else "/imports/invoices")}
            def change(transaction):
                if job is None:
                    return self.repository.create_or_get_job(import_type="file_import.confirm", import_session_id=session_id,
                        idempotency_key=f"file_import.prepare:{session_id}", payload=payload, created_by=owner,
                        stage="prepare", transaction=transaction)
                return self.repository.reprepare_job(job.import_job_id, expected_version=job.version, payload=payload, transaction=transaction)
            return store.save_import_draft_change(file_service.preview_session_persistence_payload(session.id), job_command=change)
        except Exception:
            file_service.restore_draft(before)
            raise

    def discard_files(self, *, file_service: Any, store: Any, session_id: str, owner: str) -> Any:
        self.assert_file_session_access(file_service, session_id=session_id, actor=owner)
        before = file_service.draft_checkpoint(session_id)
        job = self.session_job(session_id, owner, "file_import.confirm")
        if job is not None:
            assert_import_not_disposed(job)
        try:
            session = file_service.discard_session(session_id=session_id, imported_by=owner, authorized_job=job)
            def cancel(transaction):
                if job is not None and job.status != "canceled":
                    return self.repository.cancel_job(job.import_job_id, created_by=job.created_by, transaction=transaction)
                return None
            store.save_import_draft_change(file_service.preview_session_persistence_payload(session.id), job_command=cancel)
            return session
        except Exception:
            file_service.restore_draft(before)
            raise

    def assert_file_session_access(self, file_service: Any, *, session_id: str, actor: str) -> Any:
        session = file_service.get_session(session_id)
        job = self.session_job(session_id, actor, "file_import.confirm")
        assert_import_session_access(session_id=session_id, creator=session.imported_by, actor=actor, job=job)
        return session

    def get_accessible(self, job_id: str, owner: str) -> ImportJob:
        job = self.repository.get_job(job_id.removeprefix(IMPORT_JOB_PREFIX))
        if job is None or (job.import_type not in SHARED_IMPORT_TYPES and job.created_by != owner):
            raise KeyError(job_id)
        return job

    def session_job(self, session_id: str, owner: str, import_type: str) -> ImportJob | None:
        jobs = [job for job in self.repository.list_by_session(session_id)
                if job.import_type == import_type and (import_type in SHARED_IMPORT_TYPES or job.created_by == owner)]
        return jobs[0] if jobs else None

    def confirm(
        self, *, session_id: str, owner: str, import_type: str,
        payload: dict[str, Any], expected_version: int | None,
    ) -> ImportJob:
        jobs = [item for item in self.repository.list_by_session(session_id)
                if item.import_type == import_type and (import_type in SHARED_IMPORT_TYPES or item.created_by == owner)]
        job = jobs[0] if jobs else None
        payload = {**payload, **self.command_context(owner)}
        if job is not None:
            payload["owner_user_id"] = job.created_by
        keys = ("session_id", "selected_file_ids", "task_id", "task_version", "confirmed_item_set_hash")
        def same_scope(item):
            return all(
                sorted(item.payload.get(key) or []) == sorted(payload.get(key) or [])
                if key == "selected_file_ids" else item.payload.get(key) == payload.get(key)
                for key in keys
            )
        exact = next((item for item in jobs if item.stage == "commit" and same_scope(item)), None)
        if exact is not None:
            assert_import_not_disposed(exact)
            if requires_repreview(exact):
                raise ImportJobIdempotencyConflict("所选文件需要复核，请重新预览后确认。")
            if exact.status == "failed":
                return self.repository.retry_job(exact.import_job_id, expected_version=exact.version, command_context=self.command_context(owner))
            if exact.status in {"pending", "processing", "succeeded"}:
                return exact
            job = exact
        elif job is not None and job.stage == "commit":
            if import_type != "file_import.confirm" or job.status != "succeeded":
                raise ImportJobIdempotencyConflict("已受理的导入范围不能改变，请等待当前任务完成。")
            if type(expected_version) is not int or expected_version != job.version:
                raise ImportJobIdempotencyConflict("预览版本已变化，请重新查看后确认剩余文件。")
            return self.repository.create_or_get_job(
                import_type=import_type, import_session_id=session_id,
                idempotency_key=f"{import_type}:{session_id}:after:{job.import_job_id}",
                payload=payload, created_by=job.created_by, stage="commit",
            )
        if job is None:
            # Structured manual input and pre-migration previews already have a
            # durable reviewed session. They enter the same commit queue directly.
            return self.repository.create_or_get_job(
                import_type=import_type, import_session_id=session_id,
                idempotency_key=f"{import_type}:{session_id}", payload=payload,
                created_by=owner, stage="commit",
            )
        assert_import_not_disposed(job)
        if requires_repreview(job):
            raise ImportJobIdempotencyConflict("所选文件需要复核，请重新预览后确认。")
        if type(expected_version) is not int or expected_version < 1:
            raise ValueError("preview_version is required for this import preview.")
        return self.repository.confirm_job(
            job.import_job_id, expected_version=expected_version,
            payload={**job.payload, **payload},
        )

    def retry(self, job_id: str, owner: str) -> ImportJob:
        job = self.get_accessible(job_id, owner)
        assert_import_not_disposed(job)
        if requires_repreview(job):
            return self.repository.reprepare_job(job.import_job_id, expected_version=job.version, payload={**job.payload, **self.command_context(owner)})
        if job.status in {"pending", "processing", "succeeded", "awaiting_confirmation"}:
            return job
        if job.status != "failed":
            raise ValueError("当前任务不可重试。")
        return self.repository.retry_job(job.import_job_id, expected_version=job.version, command_context=self.command_context(owner))

    def active_payloads(self, owner: str) -> list[dict[str, Any]]:
        return [import_job_payload(job) for job in self.repository.list_jobs(created_by=owner, limit=100, include_shared=True)
                if not job.acknowledged_at and job.status != "canceled"]
