"""Shared import-task diagnostics and audited disposition for platform users."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fin_ops_platform.services.audit import AuditTrailService
from fin_ops_platform.services.import_job_queue import ImportJobIdempotencyConflict
from fin_ops_platform.services.postgres_repositories.operations_audit import PostgresOperationsAuditRepository

REASONS = {'completed_elsewhere': '已另行完成', 'not_needed': '不再继续导入'}


class ImportJobOperationsService:
    def __init__(self, repository: Any, *, file_lifecycle: Any, etc_sessions: Any) -> None:
        self.repository = repository
        self.file_lifecycle = file_lifecycle
        self.etc_sessions = etc_sessions

    def list_jobs(self, *, page: int, page_size: int, domain: str | None = None) -> dict[str, Any]:
        if page < 1 or not 1 <= page_size <= 100:
            raise ValueError('分页参数无效。')
        if domain is not None and domain not in {"imports_invoices", "imports_bank_transactions", "imports_etc_invoices"}:
            raise ValueError("导入类型无效。")
        return self.repository.list_jobs(page=page, page_size=page_size, domain=domain)

    def detail(self, job_id: str, *, actor_account: str, file_page: int = 1) -> dict[str, Any]:
        UUID(job_id)
        if file_page < 1:
            raise ValueError('文件页码必须大于零。')
        result = self.repository.detail(job_id, file_page=file_page)
        job = result['job']
        actions = []
        if not job['disposition']:
            if job['status'] == 'failed':
                actions = ['close']
            elif job['status'] == 'needs_review' and job['import_type'] in {'file_import.confirm', 'etc_invoice_import.confirm'}:
                actions = ['discard']
        job['allowed_actions'] = actions
        return result

    def dispose(self, job_id: str, payload: dict[str, Any], *, actor: dict[str, str], request_id: str) -> dict[str, Any]:
        UUID(job_id)
        version = payload.get('version')
        action, reason, note = payload.get('action'), payload.get('reason'), payload.get('note', '')
        if type(version) is not int or version < 1:
            raise ValueError('version 必须为正整数。')
        if not isinstance(action, str) or action not in {'close','discard'} or not isinstance(reason, str) or reason not in REASONS:
            raise ValueError('请选择有效的处理动作和原因。')
        if not isinstance(note, str) or len(note) > 500:
            raise ValueError('说明最多 500 字。')
        if not actor['actor_account'] or not request_id:
            raise ValueError('缺少已认证操作人或请求标识。')

        def apply(tx, job, disposition):
            if action == 'discard':
                if job['import_type'] == 'file_import.confirm':
                    self.file_lifecycle.discard_preview_session(session_id=job['import_session_id'],
                        imported_by=job['created_by'], transaction=tx)
                elif job['import_type'] == 'etc_invoice_import.confirm':
                    self.etc_sessions.discard_preview(job['import_session_id'], imported_by=job['created_by'], transaction=tx)
                else:
                    raise ImportJobIdempotencyConflict('此类任务请使用原导入入口处理。')
            AuditTrailService(PostgresOperationsAuditRepository(tx)).record_action(
                actor_id=actor['actor_id'], action='import_job.dispose', entity_type='import_job', entity_id=job_id,
                metadata={**actor, 'request_id': request_id, 'page_key': 'app-health-operations',
                          'reason': REASONS[reason], 'summary': '结束导入任务处理',
                          'description': f"{REASONS[reason]}；保留原执行结果。", 'disposition': disposition,
                          'before_status': job['status'], 'after_status': 'canceled' if action == 'discard' else job['status']},
            )
        result = self.repository.dispose(job_id, expected_version=version, action=action, reason=reason,
                                         note=note.strip(), actor=actor, request_id=request_id, on_dispose=apply)
        result['evidence'] = {
            'target': {'kind': 'import_job', 'title': '导入任务处理', 'fields': [
                {'label': '处理原因', 'value': REASONS[reason]}, {'label': '补充说明', 'value': note.strip() or '无'},
                {'label': '原执行结果', 'value': '失败' if action == 'close' else '需要复核'},
            ]},
            'changes': [{'label': '处理状态', 'before': '待处理', 'after': '已结束处理（原执行历史保留）'}],
        }
        return result
