import { useState } from "react";
import { Button, Label, ListBox, Select } from "@heroui/react";
import PageScaffold from "../components/common/PageScaffold";
import QuerySearch from "../components/common/QuerySearch";
import BusinessPeriodPicker, { nearbyBusinessYears } from "../components/common/BusinessPeriodPicker";
import StatePanel from "../components/common/StatePanel";
import TaxCertificationTable from "../components/tax/TaxCertificationTable";
import TaxCertificationSummary from "../components/tax/TaxCertificationSummary";
import TaxCertificationExportDrawer from "../components/tax/TaxCertificationExportDrawer";
import CertifiedInvoiceImportDrawer from "../components/tax/CertifiedInvoiceImportDrawer";
import { DEFAULT_MONTH } from "../contexts/MonthContext";
import { useOptionalPageActivation } from "../contexts/PageRuntimeContext";
import { useSessionPermissions } from "../contexts/SessionContext";
import { useTaxCertifications } from "../features/tax/useTaxCertifications";
import type { TaxCertificationFilters, TaxCertificationQuery, TaxExportField } from "../features/tax/types";
import "../components/tax/taxCertification.css";

export default function TaxOffsetPage() {
  const { canOperateData } = useSessionPermissions();
  const { active, activationGeneration } = useOptionalPageActivation("tax-offset");
  const [query, setQuery] = useState<TaxCertificationQuery>({ status: "all", sort_by: "issue_date", sort_direction: "desc", page: 1, page_size: 50 });
  const [search, setSearch] = useState("");
  const [importOpen, setImportOpen] = useState(false);
  const [exportSnapshot, setExportSnapshot] = useState<{ filters: TaxCertificationFilters; fields: TaxExportField[] } | null>(null);
  const { result, loading, error, refresh } = useTaxCertifications(query, active, activationGeneration);
  function changeFilters(next: Partial<TaxCertificationFilters>) { setQuery(current => ({ ...current, ...next, page: 1 })); }
  function period(field: "issue_month" | "selection_month", label: string) {
    const value = query[field] ?? DEFAULT_MONTH;
    return <BusinessPeriodPicker ariaLabel={label} label={label} allLabel="全部" allowedModes={["month"]} years={nearbyBusinessYears(value)}
      selection={{ mode: query[field] ? "month" : "all", year: value.slice(0, 4), month: value }}
      onChange={selection => changeFilters({ [field]: selection.mode === "all" ? undefined : selection.month })} />;
  }
  return <PageScaffold title="专票认证情况" className="tax-certification-page"
    query={<QuerySearch ariaLabel="搜索专票" placeholder="发票号码、销方名称或税号" value={search} onChange={setSearch}
      onSubmit={() => changeFilters({ search: search.trim() || undefined })} onClear={() => { setSearch(""); changeFilters({ search: undefined }); }} pending={loading} />}
    actions={<>{result && result.unresolved_record_count > 0 ? <Button variant="ghost" onPress={() => setImportOpen(true)}>待核对 {result.unresolved_record_count}</Button> : null}<Button variant="secondary" isDisabled={!canOperateData} onPress={() => setImportOpen(true)}>导入认证记录</Button>
      <Button variant="secondary" isDisabled={!result || result.total === 0 || loading || Boolean(error)} onPress={() => {
        if (!result) return;
        const { page: _page, page_size: _pageSize, ...filters } = query;
        setExportSnapshot({ filters, fields: result.export_fields });
      }}>导出专票清单</Button></>}>
    <div className="tax-certification-filters"><Select className="tax-certification-status" aria-label="认证状态" selectedKey={query.status} onSelectionChange={key => {
      if (key === "all" || key === "certified" || key === "uncertified") changeFilters({ status: key });
    }}><Label>认证状态</Label><Select.Trigger><Select.Value /><Select.Indicator /></Select.Trigger><Select.Popover><ListBox>
      <ListBox.Item id="all" textValue="全部">全部</ListBox.Item><ListBox.Item id="certified" textValue="已认证">已认证</ListBox.Item><ListBox.Item id="uncertified" textValue="未认证">未认证</ListBox.Item>
    </ListBox></Select.Popover></Select>{period("issue_month", "开票月份")}{period("selection_month", "勾选月份")}</div>
    {error ? <StatePanel tone="error" compact title={error}><Button variant="ghost" onPress={refresh}>重试</Button></StatePanel> : null}
    {loading ? <div role="status" className="tax-certification-loading">加载中…</div> : null}
    {result ? <div aria-busy={loading} className="tax-certification-results">
      <TaxCertificationSummary summary={result.summary} status={query.status} />
      <TaxCertificationTable result={result} query={query} loading={loading} onPageChange={page => setQuery(current => ({ ...current, page }))}
        onSortChange={sort => { if (sort.column === "issue_date" || sort.column === "selection_time") changeFilters({ sort_by: sort.column, sort_direction: sort.direction === "ascending" ? "asc" : "desc" }); }} />
    </div> : null}
    {importOpen ? <CertifiedInvoiceImportDrawer onClose={() => setImportOpen(false)} onImported={() => { refresh(); }} /> : null}
    {exportSnapshot ? <TaxCertificationExportDrawer {...exportSnapshot} onClose={() => setExportSnapshot(null)} /> : null}
  </PageScaffold>;
}
