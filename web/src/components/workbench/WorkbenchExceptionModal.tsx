import { useCallback, useEffect, useMemo, useState } from "react";

import { usePageSessionState } from "../../contexts/PageSessionStateContext";
import { applyWorkbenchException, previewWorkbenchException } from "../../features/workbench/api";
import type {
  WorkbenchExceptionAction,
  WorkbenchExceptionApplyResult,
  WorkbenchExceptionPreview,
} from "../../features/workbench/exceptionTypes";
import type { WorkbenchRecord } from "../../features/workbench/types";

type WorkbenchExceptionModalProps = {
  month: string;
  rows: WorkbenchRecord[];
  onClose: () => void;
  onApplied: (result: WorkbenchExceptionApplyResult) => void;
};

type WorkbenchExceptionDraft = {
  actionCode: string;
  note: string;
  reasonCode: string;
  dueDate: string;
};

const DRAFT_INITIAL_VALUE: WorkbenchExceptionDraft = {
  actionCode: "",
  note: "",
  reasonCode: "",
  dueDate: "",
};

const DRAFT_STATE_KEY = "workbenchExceptionModalDraft:v2";
const DRAFT_SCHEMA_VERSION = 2;

export default function WorkbenchExceptionModal({
  month,
  rows,
  onClose,
  onApplied,
}: WorkbenchExceptionModalProps) {
  const rowIds = useMemo(() => rows.map((row) => row.id), [rows]);
  const rowIdKey = rowIds.join("\u001f");
  const [preview, setPreview] = useState<WorkbenchExceptionPreview | null>(null);
  const [isPreviewLoading, setIsPreviewLoading] = useState(true);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [applyError, setApplyError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [extraPayload, setExtraPayload] = useState<Record<string, string>>({});
  const draftSession = usePageSessionState<WorkbenchExceptionDraft>({
    pageKey: "reconciliation-workbench",
    stateKey: DRAFT_STATE_KEY,
    version: DRAFT_SCHEMA_VERSION,
    initialValue: DRAFT_INITIAL_VALUE,
    ttlMs: 2 * 60 * 60 * 1000,
    storage: "session",
    validate: isWorkbenchExceptionDraft,
    debounceMs: 0,
  });
  const draft = draftSession.value;
  const setDraft = draftSession.setValue;

  useEffect(() => {
    let active = true;
    setIsPreviewLoading(true);
    setPreviewError(null);
    setApplyError(null);
    setPreview(null);

    void previewWorkbenchException({ month, rowIds })
      .then((result) => {
        if (!active) {
          return;
        }
        setPreview(result);
        setIsPreviewLoading(false);
      })
      .catch((error) => {
        if (!active) {
          return;
        }
        setPreviewError(readErrorMessage(error));
        setIsPreviewLoading(false);
      });

    return () => {
      active = false;
    };
  }, [month, rowIdKey, rowIds]);

  const automaticActions = preview?.automaticActions ?? [];
  const availableActions = preview?.availableActions ?? [];
  const submitActions = useMemo(
    () => uniqueActions([...automaticActions, ...availableActions]),
    [automaticActions, availableActions],
  );
  const selectedAction = useMemo(
    () => {
      const explicitAction = submitActions.find((action) => action.actionCode === draft.actionCode);
      if (explicitAction) {
        return explicitAction;
      }
      if (!draft.actionCode && submitActions.length === 1) {
        return submitActions[0];
      }
      return null;
    },
    [draft.actionCode, submitActions],
  );
  const missingRequiredFields = useMemo(
    () => selectedAction?.requiredFields.filter((field) => !fieldValue(field, draft, extraPayload).trim()) ?? [],
    [draft, extraPayload, selectedAction],
  );
  const canSubmit = Boolean(preview?.canApply && selectedAction && missingRequiredFields.length === 0 && !isSubmitting);

  const updateDraft = useCallback((patch: Partial<WorkbenchExceptionDraft>) => {
    setDraft((current) => ({ ...current, ...patch }));
  }, [setDraft]);

  const handleFieldChange = (field: string, value: string) => {
    if (field === "note") {
      updateDraft({ note: value });
      return;
    }
    if (field === "reason_code") {
      updateDraft({ reasonCode: value });
      return;
    }
    if (field === "due_date") {
      updateDraft({ dueDate: value });
      return;
    }
    setExtraPayload((current) => ({ ...current, [field]: value }));
  };

  const buildPayload = () => {
    if (!selectedAction) {
      return {};
    }
    const payload: Record<string, unknown> = {};
    if (draft.note.trim()) {
      payload.note = draft.note.trim();
    }
    if (draft.reasonCode.trim()) {
      payload.reason_code = draft.reasonCode.trim();
    }
    if (draft.dueDate.trim()) {
      payload.due_date = draft.dueDate.trim();
    }
    selectedAction.requiredFields.forEach((field) => {
      if (field === "note" || field === "reason_code" || field === "due_date") {
        return;
      }
      const value = fieldValue(field, draft, extraPayload).trim();
      if (value) {
        payload[field] = value;
      }
    });
    return payload;
  };

  const handleSubmit = async () => {
    if (!preview || !selectedAction || !canSubmit) {
      return;
    }
    setIsSubmitting(true);
    setApplyError(null);
    try {
      const result = await applyWorkbenchException({
        month,
        rowIds,
        scenarioCode: preview.scenario.scenarioCode,
        actionCode: selectedAction.actionCode,
        payload: buildPayload(),
      });
      draftSession.reset();
      onApplied(result);
      onClose();
    } catch (error) {
      setApplyError(readErrorMessage(error));
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div aria-label="统一异常处理" aria-modal="true" className="detail-modal-backdrop" role="dialog">
      <div className="detail-modal workbench-exception-modal" onClick={(event) => event.stopPropagation()}>
        <header className="detail-modal-header">
          <div>
            <div className="modal-eyebrow">统一异常处理</div>
            <h2>统一异常处理</h2>
          </div>
          <button aria-label="关闭统一异常处理" className="detail-close-btn" type="button" onClick={onClose}>
            关闭
          </button>
        </header>

        <div className="detail-modal-body">
          <div className="oa-bank-exception-summary">
            <span className="zone-selection-pill">已选 {rows.length}</span>
            <span className="zone-selection-pill">OA {rows.filter((row) => row.recordType === "oa").length}</span>
            <span className="zone-selection-pill">流水 {rows.filter((row) => row.recordType === "bank").length}</span>
            <span className="zone-selection-pill">发票 {rows.filter((row) => row.recordType === "invoice").length}</span>
          </div>

          {isPreviewLoading ? <div className="state-panel">正在加载异常预览</div> : null}
          {previewError ? (
            <div className="state-panel error">
              <strong>异常预览加载失败</strong>
              <div>{previewError}</div>
            </div>
          ) : null}
          {preview ? (
            <>
              <section className="oa-bank-equation-card">
                <div className="oa-bank-equation-row">
                  <span>业务线</span>
                  <strong>{businessLineLabel(preview.scenario.businessLine)}</strong>
                </div>
                <div className="oa-bank-equation-row">
                  <span>场景</span>
                  <strong>{preview.scenario.scenarioLabel || preview.scenario.scenarioCode}</strong>
                </div>
                <div className="oa-bank-equation-row">
                  <span>规则版本</span>
                  <strong>{preview.ruleVersion || "—"}</strong>
                </div>
              </section>

              <section className="oa-bank-equation-card">
                <h3>金额摘要</h3>
                <AmountRow label="OA合计" value={preview.amountSummary.oaTotal} />
                <AmountRow label="支出流水合计" value={preview.amountSummary.bankExpenseTotal} />
                <AmountRow label="收入流水合计" value={preview.amountSummary.bankIncomeTotal} />
                <AmountRow label="进项发票合计" value={preview.amountSummary.inputInvoiceTotal} />
                <AmountRow label="销项发票合计" value={preview.amountSummary.outputInvoiceTotal} />
                <div className="oa-bank-equation-row">
                  <span>差异关系</span>
                  <strong>{preview.amountSummary.relation}</strong>
                </div>
              </section>

              {preview.candidateEvidence.length > 0 ? (
                <section className="oa-bank-equation-card">
                  <h3>系统自动识别证据</h3>
                  <div className="exception-evidence-list">
                    {preview.candidateEvidence.map((evidence, index) => (
                      <div key={evidence.id ?? `${evidence.label}-${index}`} className="exception-evidence-item">
                        <strong>{evidence.label}</strong>
                        {evidence.detail ? <span>{evidence.detail}</span> : null}
                      </div>
                    ))}
                  </div>
                </section>
              ) : null}

              {preview.warnings.length > 0 ? (
                <section className="oa-bank-equation-card">
                  <h3>Warnings</h3>
                  {preview.warnings.map((warning, index) => (
                    <div key={warning.code || index} className={`state-panel ${warning.severity === "error" ? "error" : ""}`}>
                      {warning.message || warning.code}
                    </div>
                  ))}
                </section>
              ) : null}

              <ActionSection
                actions={automaticActions}
                selectedActionCode={selectedAction?.actionCode ?? ""}
                title="系统自动动作"
                tone="automatic"
                onSelect={(actionCode) => updateDraft({ actionCode })}
              />

              <section className="oa-bank-equation-card">
                <h3>人工可选动作</h3>
                {availableActions.length === 0 ? (
                  <div className="state-panel">后端未返回可执行人工动作。</div>
                ) : (
                  <div className="exception-action-list">
                    {availableActions.map((action) => (
                      <label key={action.actionCode} className="exception-action-option manual">
                        <input
                          aria-label={`${action.label} ${resultStatusLabel(action.resultStatus)}`}
                          checked={draft.actionCode === action.actionCode}
                          name="workbench-exception-action"
                          type="radio"
                          value={action.actionCode}
                          onChange={() => updateDraft({ actionCode: action.actionCode })}
                        />
                        <span>
                          <strong>{action.label || action.actionCode}</strong>
                          <span>{resultStatusLabel(action.resultStatus)}</span>
                          {action.description ? <small>{action.description}</small> : null}
                        </span>
                      </label>
                    ))}
                  </div>
                )}
              </section>

              {selectedAction ? (
                <section className="oa-bank-equation-card">
                  <h3>必填字段</h3>
                  {selectedAction.requiredFields.length === 0 ? (
                    <div className="state-panel">当前动作没有后端声明的必填字段。</div>
                  ) : (
                    selectedAction.requiredFields.map((field) => (
                      <RequiredField
                        key={field}
                        field={field}
                        value={fieldValue(field, draft, extraPayload)}
                        onChange={(value) => handleFieldChange(field, value)}
                      />
                    ))
                  )}
                </section>
              ) : null}
            </>
          ) : null}
          {applyError ? (
            <div className="state-panel error">
              <strong>异常处理提交失败</strong>
              <div>{applyError}</div>
            </div>
          ) : null}
        </div>

        <div className="detail-modal-footer">
          <button className="secondary-button" disabled={isSubmitting} type="button" onClick={onClose}>
            取消
          </button>
          {preview && !preview.canApply ? <span className="state-panel">当前预览不可提交。</span> : null}
          {preview && submitActions.length > 0 ? (
            <button className="primary-button" disabled={!canSubmit} type="button" onClick={handleSubmit}>
              {isSubmitting ? "提交中..." : "提交处理"}
            </button>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function isWorkbenchExceptionDraft(value: unknown): value is WorkbenchExceptionDraft {
  if (!value || typeof value !== "object") {
    return false;
  }
  const draft = value as Record<string, unknown>;
  return (
    typeof draft.actionCode === "string"
    && typeof draft.note === "string"
    && typeof draft.reasonCode === "string"
    && typeof draft.dueDate === "string"
  );
}

function AmountRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="oa-bank-equation-row">
      <span>{label}</span>
      <strong>{formatAmount(value)}</strong>
    </div>
  );
}

function uniqueActions(actions: WorkbenchExceptionAction[]) {
  const seen = new Set<string>();
  const result: WorkbenchExceptionAction[] = [];
  actions.forEach((action) => {
    if (!action.actionCode || seen.has(action.actionCode)) {
      return;
    }
    seen.add(action.actionCode);
    result.push(action);
  });
  return result;
}

function ActionSection({
  actions,
  selectedActionCode,
  title,
  tone,
  onSelect,
}: {
  actions: WorkbenchExceptionAction[];
  selectedActionCode?: string;
  title: string;
  tone: "automatic" | "manual";
  onSelect?: (actionCode: string) => void;
}) {
  if (actions.length === 0) {
    return null;
  }
  return (
    <section className="oa-bank-equation-card">
      <h3>{title}</h3>
      <div className="exception-action-list">
        {actions.map((action) => (
          <label key={action.actionCode} className={`exception-action-option ${tone}`}>
            {onSelect ? (
              <input
                aria-label={`${action.label} ${resultStatusLabel(action.resultStatus)}`}
                checked={selectedActionCode === action.actionCode}
                name="workbench-exception-action"
                type="radio"
                value={action.actionCode}
                onChange={() => onSelect(action.actionCode)}
              />
            ) : null}
            <span className="exception-action-source">{tone === "automatic" ? "自动识别" : "人工确认"}</span>
            <span>
              <strong>{action.label || action.actionCode}</strong>
              <span>{resultStatusLabel(action.resultStatus)}</span>
              {action.description ? <small>{action.description}</small> : null}
            </span>
          </label>
        ))}
      </div>
    </section>
  );
}

function RequiredField({
  field,
  value,
  onChange,
}: {
  field: string;
  value: string;
  onChange: (value: string) => void;
}) {
  const label = fieldLabel(field);
  if (field === "note") {
    return (
      <label className="field-block">
        <span className="field-label">{label}</span>
        <textarea
          aria-label={label}
          className="field-textarea"
          rows={3}
          value={value}
          onChange={(event) => onChange(event.target.value)}
        />
      </label>
    );
  }
  return (
    <label className="field-block">
      <span className="field-label">{label}</span>
      <input
        aria-label={label}
        className="field-input"
        type={field === "due_date" ? "date" : "text"}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}

function fieldLabel(field: string) {
  if (field === "note") {
    return "备注";
  }
  if (field === "reason_code") {
    return "原因代码";
  }
  if (field === "due_date") {
    return "到期日期";
  }
  return field;
}

function fieldValue(field: string, draft: WorkbenchExceptionDraft, extraPayload: Record<string, string>) {
  if (field === "note") {
    return draft.note;
  }
  if (field === "reason_code") {
    return draft.reasonCode;
  }
  if (field === "due_date") {
    return draft.dueDate;
  }
  return extraPayload[field] ?? "";
}

function businessLineLabel(value: string) {
  if (value === "expense") {
    return "支出";
  }
  if (value === "income") {
    return "收入";
  }
  if (value === "data_anomaly") {
    return "数据异常";
  }
  return value || "—";
}

function resultStatusLabel(value: string) {
  if (value === "closed") {
    return "处理后闭环";
  }
  if (value === "open") {
    return "进入待处理";
  }
  return value || "待后端确认";
}

function formatAmount(value: string) {
  const numericValue = Number(value.replace(/,/g, ""));
  if (!Number.isFinite(numericValue)) {
    return value || "0.00";
  }
  return new Intl.NumberFormat("zh-CN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(numericValue);
}

function readErrorMessage(error: unknown) {
  if (error instanceof Error) {
    try {
      const payload = JSON.parse(error.message) as { message?: string };
      if (payload.message?.trim()) {
        return payload.message.trim();
      }
    } catch {
      if (error.message.trim()) {
        return error.message.trim();
      }
    }
  }
  return "操作失败，请稍后重试。";
}
