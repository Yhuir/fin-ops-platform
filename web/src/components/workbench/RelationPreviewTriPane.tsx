import { memo, useMemo } from "react";
import { Chip } from "@heroui/react";
import BankAccountValue from "../BankAccountValue";
import PreviewRecordDetails from "./PreviewRecordDetails";

import { formatMoney } from "../../features/money";
import {
  buildWorkbenchGroupDisplayLayout,
  compactWorkbenchBankAccountLabel,
} from "../../features/workbench/groupDisplayModel";
import type {
  WorkbenchRelationGroup,
  WorkbenchRecord,
  WorkbenchRecordType,
} from "../../features/workbench/types";
import BankSplitChips from "../../features/bankSplits/BankSplitChips";

export type RelationPreviewTriPaneProps = {
  title: string;
  side: "before" | "after";
  testId?: string;
  groups: WorkbenchRelationGroup[];
  referenceGroups?: WorkbenchRelationGroup[];
  totals: { oaTotal: string; bankTotal: string; invoiceTotal: string };
  status?: "matched" | "mismatch" | "unknown" | (string & {});
  mismatchFields: string[];
};

type PreviewPaneConfig = {
  id: WorkbenchRecordType;
  title: string;
  mismatchField: string;
};
const PREVIEW_PANES: PreviewPaneConfig[] = [
  { id: "oa", title: "OA", mismatchField: "oa_total" },
  { id: "bank", title: "流水", mismatchField: "bank_total" },
  { id: "invoice", title: "发票", mismatchField: "invoice_total" },
];
const PREVIEW_STATUS_LABELS = {
  matched: "金额一致",
  mismatch: "金额不一致",
  pending: "金额待核对",
} as const;

function RelationPreviewTriPane({
  title,
  side,
  testId,
  groups,
  referenceGroups = groups,
  totals,
  status,
  mismatchFields,
}: RelationPreviewTriPaneProps) {
  // Keep the first unchanged group in the same band while alternating adjacent groups.
  const bandOffset = useMemo(() => {
    const referenceBands = new Map(referenceGroups.map((group, index) => [group.id, index % 2]));
    const anchor = groups.findIndex((group) => referenceBands.has(group.id));
    return anchor < 0 ? 0 : (referenceBands.get(groups[anchor].id)! + anchor) % 2;
  }, [groups, referenceGroups]);
  const rowCountByPane = useMemo(
    () => ({
      oa: groups.reduce((sum, group) => sum + group.rows.oa.length, 0),
      bank: new Set(
        groups.flatMap((group) =>
          group.rows.bank.map((row) =>
            row.isSplit ? row.parentRowId : row.id,
          ),
        ),
      ).size,
      invoice: groups.reduce(
        (sum, group) => sum + group.rows.invoice.length,
        0,
      ),
    }),
    [groups],
  );
  const previewStatus = resolvePreviewStatus(
    status,
    mismatchFields,
    totals,
    rowCountByPane,
  );
  const mismatch = resolveVisualMismatchFields(
    status,
    totals,
    mismatchFields,
    rowCountByPane,
  );
  const delta = buildDeltaAmount(status, totals, rowCountByPane);
  return (
    <section
      className={`relation-preview-section relation-preview-section-${side}`}
      data-testid={testId}
      id={testId}
    >
      <div className="relation-preview-sticky-head">
        <div className="relation-preview-section-heading">
          <h3>{title}</h3>
          <span
            className={`relation-preview-status relation-preview-status-${previewStatus}`}
          >
            {PREVIEW_STATUS_LABELS[previewStatus]}
          </span>
          {delta ? (
            <span
              className="relation-preview-delta"
              data-testid="relation-preview-delta"
            >
              差额 {delta}
            </span>
          ) : null}
        </div>
        <div
          className="relation-preview-columns"
          data-testid="relation-preview-summary"
        >
          {PREVIEW_PANES.map((pane) => (
            <div
              key={pane.id}
              className={
                mismatch.includes(pane.mismatchField)
                  ? "relation-preview-column mismatch"
                  : "relation-preview-column"
              }
              data-testid={`pane-${pane.id}`}
            >
              <span>
                {pane.title}{" "}
                <small>
                  {rowCountByPane[pane.id]}
                  {pane.id === "bank" ? " 笔" : " 项"}
                </small>
              </span>
              <strong
                data-testid={`relation-preview-summary-metric-${pane.id}`}
              >
                {formatDisplayAmount(
                  resolvePaneTotal(totals, pane.id),
                  rowCountByPane[pane.id] > 0,
                )}
              </strong>
            </div>
          ))}
        </div>
      </div>
      <div className="relation-preview-groups" data-testid="tri-pane">
        {groups.length ? (
          groups.map((group, index) => <PreviewGroup key={group.id} group={group} band={(index + bandOffset) % 2} />)
        ) : (
          <div className="relation-preview-empty">暂无记录</div>
        )}
      </div>
    </section>
  );
}

const PreviewGroup = memo(function PreviewGroup({
  group,
  band,
}: {
  group: WorkbenchRelationGroup;
  band: number;
}) {
  const layout = useMemo(
    () => buildWorkbenchGroupDisplayLayout(group),
    [group],
  );
  const segmentCount = layout?.segments.length || 1;
  return (
    <div
      className="relation-preview-group"
      data-band={band}
      data-testid={`candidate-group-${group.id}`}
      role="rowgroup"
      aria-label="关联组"
    >
      {PREVIEW_PANES.map((pane, column) => {
        if (
          layout &&
          layout.segments.length &&
          layout.segmentedPaneIds.includes(pane.id)
        ) {
          return layout.segments.flatMap((segment, index) => (segment.rowSpans?.[pane.id] === 0 ? [] : [
            <div
              key={`${pane.id}-${segment.id}`}
              className="relation-preview-group-cell"
              data-pane={pane.id}
              data-segment={segment.id}
              style={{ gridColumn: column + 1, gridRow: segment.rowSpans?.[pane.id] ? `${index + 1} / span ${segment.rowSpans[pane.id]}` : index + 1 }}
            >
              <PreviewRecords records={segment.rows[pane.id]} />
            </div>
          ]));
        }
        return (
          <div
            key={pane.id}
            className="relation-preview-group-cell"
            data-pane={pane.id}
            style={{
              gridColumn: column + 1,
              gridRow: `1 / span ${segmentCount}`,
            }}
          >
            <PreviewRecords records={group.rows[pane.id]} />
          </div>
        );
      })}
    </div>
  );
});

function PreviewRecords({ records }: { records: WorkbenchRecord[] }) {
  const byIdentity = new Map<string, WorkbenchRecord[]>();
  for (const row of records) {
    const key =
      row.recordType === "bank" && row.isSplit ? row.parentRowId! : row.id;
    const members = byIdentity.get(key);
    if (members) members.push(row);
    else byIdentity.set(key, [row]);
  }
  if (!records.length)
    return <span className="relation-preview-empty-cell">—</span>;
  return (
    <>
      {Array.from(byIdentity, ([identity, members]) => (
        <PreviewRecord key={identity} row={members[0]} members={members} />
      ))}
    </>
  );
}

function PreviewRecord({
  row,
  members,
}: {
  row: WorkbenchRecord;
  members: WorkbenchRecord[];
}) {
  const v = row.tableValues;
  const identity =
    row.recordType === "oa"
      ? [
          v.applicant,
          v.projectName,
          v.counterparty,
          row.amount,
          v.applicationTime,
        ]
      : row.recordType === "bank"
        ? [
            v.transactionTime,
            row.counterparty,
            row.isSplit ? row.parentAmount : row.amount,
          ]
        : [
            v.sellerTaxId,
            v.sellerName,
            v.buyerTaxId,
            v.buyerName,
            v.invoiceNo,
            v.grossAmount,
          ];
  const memberIds = new Set(members.map((member) => member.id));
  const parts = row.bankSplitParts?.filter((part) => memberIds.has(part.id));
  const details: [string, string][] = row.recordType === "oa"
    ? [["项目", v.projectName], ["申请人", v.applicant], ["申请时间", v.applicationTime], ["申请事由", v.reason]]
    : row.recordType === "bank"
      ? [["对方户名", row.counterparty], ["银行账户", v.paymentAccount], ["交易时间", v.transactionTime]]
      : [["销方", v.sellerName], ["销方识别号", v.sellerTaxId], ["购方", v.buyerName], ["购方识别号", v.buyerTaxId], ["发票号码", v.invoiceNo], ["开票日期", v.issueDate]];
  const name = row.recordType === "oa" ? v.projectName : row.recordType === "bank" ? row.counterparty : v.sellerName;
  return (
    <div
      className="relation-preview-record"
      role="row"
      aria-label={identity.filter(Boolean).join(" ")}
      data-member-ids={members.map((member) => member.id).join(" ")}
    >
      <div
        role="cell"
        className="relation-preview-record-content"
      >
        {!row.supportingDocuments ? (
          <div className="relation-preview-record-heading">
            <strong className="relation-preview-name">{name}</strong>
            <PreviewRecordDetails key={JSON.stringify(details)} label={`${row.recordType === "oa" ? "OA" : row.recordType === "bank" ? "流水" : "发票"}详情`} fields={details} />
          </div>
        ) : null}
        {row.recordType === "oa" ? (
          <>
            <div className="relation-preview-record-line">
              <span>{v.applicant}</span>
              <strong className="relation-preview-money">
                {formatMoney(row.amount, "—")}
              </strong>
            </div>
          </>
        ) : row.recordType === "bank" ? (
          <>
            <Chip size="sm" variant="soft" color={v.direction === "支出" ? "danger" : v.direction === "收入" ? "success" : "default"} className="relation-preview-payment">
              <span>{v.direction === "支出" ? "支" : v.direction === "收入" ? "收" : v.direction}</span>
              <strong className="relation-preview-money">
                {formatMoney(row.isSplit ? row.parentAmount : row.amount, "—")}
              </strong>
            </Chip>
            <BankAccountValue value={compactWorkbenchBankAccountLabel(v.paymentAccount)} variant="tag" />
            {row.isSplit ? (
              <BankSplitChips parts={parts ?? []} />
            ) : row.categoryLabelPath?.length ? (
              <Chip size="sm" variant="soft" className="relation-preview-tag">
                {row.categoryLabelPath.join(" / ")}
              </Chip>
            ) : null}
          </>
        ) : row.supportingDocuments ? (
          <>
            {row.supportingDocuments.map((document) => (
              <a
                key={document.id}
                href={document.contentUrl}
                target="_blank"
                rel="noopener noreferrer"
              >
                {document.fileName}
              </a>
            ))}
            <strong className="relation-preview-money">
              凭证金额 {formatMoney(row.supportingDocumentAmount, "—")}
            </strong>
          </>
        ) : (
          <>
            <strong className="relation-preview-money">
              {formatMoney(v.grossAmount, "—")}
            </strong>
          </>
        )}
      </div>
    </div>
  );
}

export default memo(RelationPreviewTriPane);

function resolvePaneTotal(
  totals: RelationPreviewTriPaneProps["totals"],
  paneId: WorkbenchRecordType,
) {
  if (paneId === "oa") {
    return totals.oaTotal;
  }
  if (paneId === "bank") {
    return totals.bankTotal;
  }
  return totals.invoiceTotal;
}

function resolvePreviewStatus(
  amountStatus: RelationPreviewTriPaneProps["status"],
  mismatchFields: string[],
  totals: RelationPreviewTriPaneProps["totals"],
  rowCountByPane: Record<WorkbenchRecordType, number>,
): keyof typeof PREVIEW_STATUS_LABELS {
  if (amountStatus === "matched") {
    return "matched";
  }
  if (amountStatus === "unknown") {
    return "pending";
  }
  if (amountStatus === "mismatch") {
    return "mismatch";
  }

  const visualMismatchFields = resolveVisualMismatchFields(
    amountStatus,
    totals,
    mismatchFields,
    rowCountByPane,
  );
  if (visualMismatchFields.length > 0) {
    return "mismatch";
  }

  const totalValues = PREVIEW_PANES.filter(
    (pane) => rowCountByPane[pane.id] > 0,
  ).map((pane) => resolvePaneTotal(totals, pane.id));
  if (
    totalValues.length > 0 &&
    totalValues.some((value) => parseMoneyAmount(value) === null)
  ) {
    return "pending";
  }

  return "matched";
}

function parseMoneyAmount(value: string) {
  const normalized = value.replace(/,/g, "").replace(/\s/g, "");
  if (!normalized || normalized === "-") {
    return null;
  }

  const amount = Number(normalized);
  return Number.isFinite(amount) ? amount : null;
}

function formatMoneyDelta(value: number) {
  return formatMoney(value);
}

function formatDisplayAmount(value: string, hasRows: boolean) {
  if (!hasRows) {
    return "-";
  }
  return parseMoneyAmount(value) === null ? "-" : formatMoney(value);
}

function resolveComparableAmounts(
  totals: RelationPreviewTriPaneProps["totals"],
  rowCountByPane: Record<WorkbenchRecordType, number>,
) {
  return PREVIEW_PANES.filter((pane) => rowCountByPane[pane.id] > 0)
    .map((pane) => {
      const displayValue = resolvePaneTotal(totals, pane.id);
      return {
        pane,
        amount: parseMoneyAmount(displayValue),
      };
    })
    .filter((total) => total.amount !== null) as Array<{
    pane: PreviewPaneConfig;
    amount: number;
  }>;
}

function resolveVisualMismatchFields(
  amountStatus: RelationPreviewTriPaneProps["status"],
  totals: RelationPreviewTriPaneProps["totals"],
  mismatchFields: string[],
  rowCountByPane: Record<WorkbenchRecordType, number>,
) {
  const comparableAmounts = resolveComparableAmounts(totals, rowCountByPane);
  const nonEmptyMismatchFields = mismatchFields.filter((field) =>
    PREVIEW_PANES.some(
      (pane) => pane.mismatchField === field && rowCountByPane[pane.id] > 0,
    ),
  );

  if (amountStatus === "matched" || amountStatus === "unknown") {
    return [];
  }
  if (amountStatus === "mismatch" && nonEmptyMismatchFields.length > 0) {
    return nonEmptyMismatchFields;
  }

  if (comparableAmounts.length < 2) {
    return nonEmptyMismatchFields;
  }

  if (comparableAmounts.length === 2) {
    const [left, right] = comparableAmounts;
    return areMoneyAmountsEqual(left.amount, right.amount)
      ? []
      : [left.pane.mismatchField, right.pane.mismatchField];
  }

  const amountGroups = comparableAmounts.reduce<
    Array<typeof comparableAmounts>
  >((groups, total) => {
    const existingGroup = groups.find((group) =>
      areMoneyAmountsEqual(group[0].amount, total.amount),
    );
    if (existingGroup) {
      existingGroup.push(total);
    } else {
      groups.push([total]);
    }
    return groups;
  }, []);

  if (amountGroups.length === 1) {
    return [];
  }

  if (amountGroups.length === 2) {
    const isolatedGroup = amountGroups.find((group) => group.length === 1);
    return isolatedGroup
      ? [isolatedGroup[0].pane.mismatchField]
      : comparableAmounts.map((total) => total.pane.mismatchField);
  }

  return comparableAmounts.map((total) => total.pane.mismatchField);
}

function buildDeltaAmount(
  amountStatus: RelationPreviewTriPaneProps["status"],
  totals: RelationPreviewTriPaneProps["totals"],
  rowCountByPane: Record<WorkbenchRecordType, number>,
) {
  if (amountStatus && amountStatus !== "mismatch") {
    return null;
  }
  const comparableAmounts = resolveComparableAmounts(totals, rowCountByPane);
  if (comparableAmounts.length < 2) {
    return null;
  }

  const amounts = comparableAmounts.map((total) => total.amount);
  return formatMoneyDelta(Math.max(...amounts) - Math.min(...amounts));
}

function areMoneyAmountsEqual(left: number, right: number) {
  return Math.abs(left - right) < 0.005;
}
