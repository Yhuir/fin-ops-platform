import { useState } from "react";
import { Button } from "@heroui/react";
import PageScaffold from "../components/common/PageScaffold";
import PageStatisticsPopover from "../components/common/PageStatisticsPopover";
import QuerySearch from "../components/common/QuerySearch";
import BusinessPeriodPicker, { nearbyBusinessYears } from "../components/common/BusinessPeriodPicker";
import SegmentedControl from "../components/common/SegmentedControl";
import StatePanel from "../components/common/StatePanel";
import TaxCertificationTable from "../components/tax/TaxCertificationTable";
import TaxCertificationSummary from "../components/tax/TaxCertificationSummary";
import TaxCertificationExportDrawer from "../components/tax/TaxCertificationExportDrawer";
import CertifiedInvoiceImportDrawer from "../components/tax/CertifiedInvoiceImportDrawer";
import { DEFAULT_MONTH } from "../contexts/MonthContext";
import { useOptionalPageActivation } from "../contexts/PageRuntimeContext";
import { useSessionPermissions } from "../contexts/SessionContext";
import { useTaxCertifications } from "../features/tax/useTaxCertifications";
import type { TaxCertificationFilters, TaxCertificationQuery, TaxCertificationStatus, TaxExportField } from "../features/tax/types";
import "../components/tax/taxCertification.css";

export default function TaxOffsetPage() {
  const { canOperateData } = useSessionPermissions();
  const { active, activationGeneration } = useOptionalPageActivation("tax-offset");
  const [query, setQuery] = useState<TaxCertificationQuery>({ status: "all", sort_by: "issue_date", sort_direction: "desc", page: 1, page_size: 50 });
  const [search, setSearch] = useState("");
  const [importOpen, setImportOpen] = useState(false);
  const [exportSnapshot, setExportSnapshot] = useState<{ filters: TaxCertificationFilters; fields: TaxExportField[] } | null>(null);
  const { result, loading, error, refresh } = useTaxCertifications(query, active, activationGeneration);
  const inventory = result?.inventory_statistics;
  function changeFilters(next: Partial<TaxCertificationFilters>) { setQuery(current => ({ ...current, ...next, page: 1 })); }
  function period(prefix: "issue" | "selection", label: string) {
    const month = query[`${prefix}_month`]; const year = query[`${prefix}_year`];
    const value = month ?? (year ? `${year}-01` : DEFAULT_MONTH);
    return <BusinessPeriodPicker compact ariaLabel={label} label={label} allLabel="全部" years={nearbyBusinessYears(value)}
      selection={{ mode: month ? "month" : year ? "year" : "all", year: value.slice(0, 4), month: value }}
      onChange={selection => changeFilters({ [`${prefix}_year`]: selection.mode === "year" ? selection.year : undefined,
        [`${prefix}_month`]: selection.mode === "month" ? selection.month : undefined })} />;
  }
  return <PageScaffold fillViewport title="专票认证情况" className="tax-certification-page"
    titleAccessory={<div className="tax-certification-inventory" title="全部进项发票，不随下方筛选变化">
      <PageStatisticsPopover ariaLabel="进项发票统计" loading={loading} coreItems={[
        { label: "进项发票", value: inventory?.input_invoice_count, unit: "张" },
        { label: "专票", value: inventory?.special_invoice_count, unit: "张" },
        { label: "普票", value: inventory?.general_invoice_count, unit: "张" },
        { label: "通行费", value: inventory?.toll_invoice_count, unit: "张" },
        { label: "其他", value: inventory?.other_invoice_count, unit: "张" },
      ]} detailItems={inventory && inventory.unclassified_invoice_count > 0
        ? [{ label: "未识别票种", value: inventory.unclassified_invoice_count, unit: "张", tone: "warning" }]
        : []} />
    </div>}
    query={<QuerySearch ariaLabel="搜索专票" placeholder="票号、销方名称或税号" value={search} onChange={setSearch} maxLength={200}
      onSubmit={() => changeFilters({ search: search.trim() || undefined })} onClear={() => { setSearch(""); changeFilters({ search: undefined }); }} pending={loading} />}
    actions={<><Button variant="secondary" isDisabled={!result || result.total === 0 || loading || Boolean(error)} onPress={() => {
      if (!result) return;
      const { page: _page, page_size: _pageSize, ...filters } = query;
      setExportSnapshot({ filters, fields: result.export_fields });
    }}>导出专票清单</Button><Button variant="primary" isDisabled={!canOperateData} onPress={() => setImportOpen(true)}>导入认证记录</Button></>}>
    <section className="tax-certification-results finance-table-layout" aria-busy={loading}>
      <div className="tax-certification-toolbar">
        <SegmentedControl<TaxCertificationStatus> label="认证状态" value={query.status} onChange={status => changeFilters({ status })}
          options={[{ key: "all", label: "全部" }, { key: "uncertified", label: "未认证" }, { key: "certified", label: "已认证" }]} />
        <TaxCertificationSummary summary={result?.summary ?? null} />
        <div className="tax-certification-periods">{period("issue", "开票月份")}{period("selection", "勾选月份")}</div>
      </div>
      {error ? <StatePanel tone="error" compact title={error}><Button variant="ghost" onPress={refresh}>重试</Button></StatePanel> : null}
      {loading ? <div role="status" className="tax-certification-loading">{result ? "正在更新当前筛选结果…" : "加载中…"}</div> : null}
      <div className="finance-page-table-frame">
        <TaxCertificationTable result={result} query={query} loading={loading} error={Boolean(error)} onPageChange={page => setQuery(current => ({ ...current, page }))}
          onSortChange={sort => { if (sort.column === "issue_date" || sort.column === "selection_time") changeFilters({ sort_by: sort.column, sort_direction: sort.direction === "ascending" ? "asc" : "desc" }); }} />
      </div>
    </section>
    {importOpen ? <CertifiedInvoiceImportDrawer onClose={() => setImportOpen(false)} onImported={refresh} /> : null}
    {exportSnapshot ? <TaxCertificationExportDrawer {...exportSnapshot} onClose={() => setExportSnapshot(null)} /> : null}
  </PageScaffold>;
}
