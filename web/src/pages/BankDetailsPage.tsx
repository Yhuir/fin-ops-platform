import { useEffect, useMemo, useState } from "react";

import { fetchBankDetailAccounts, fetchBankDetailTransactions } from "../features/bankDetails/api";
import type { BankDateFilter, BankDetailAccount, BankDetailTransaction } from "../features/bankDetails/types";

const TODAY = new Date(2026, 4, 2);

function formatDate(date: Date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function daysAgo(days: number) {
  const date = new Date(TODAY);
  date.setDate(date.getDate() - days);
  return date;
}

function endOfMonth(year: number, monthIndex: number) {
  return new Date(year, monthIndex + 1, 0);
}

function createDateFilter(preset: BankDateFilter["preset"], monthValue = "2026-05"): BankDateFilter {
  if (preset === "previous_month") {
    return { preset, dateFrom: "2026-04-01", dateTo: "2026-04-30" };
  }
  if (preset === "last_7_days") {
    return { preset, dateFrom: formatDate(daysAgo(6)), dateTo: formatDate(TODAY) };
  }
  if (preset === "last_30_days") {
    return { preset, dateFrom: formatDate(daysAgo(29)), dateTo: formatDate(TODAY) };
  }
  if (preset === "current_year") {
    return { preset, dateFrom: "2026-01-01", dateTo: "2026-12-31" };
  }
  if (preset === "month") {
    const [year, month] = monthValue.split("-").map(Number);
    return {
      preset,
      dateFrom: `${year}-${String(month).padStart(2, "0")}-01`,
      dateTo: formatDate(endOfMonth(year, month - 1)),
    };
  }
  return { preset: "current_month", dateFrom: "2026-05-01", dateTo: "2026-05-31" };
}

function displayBalance(value: string | null) {
  return value && value.trim() ? formatMoney(value) : "余额为空";
}

function formatMoney(value: string | null) {
  if (!value || !value.trim()) {
    return "";
  }
  const parsed = Number(value.replace(/,/g, ""));
  if (!Number.isFinite(parsed)) {
    return value;
  }
  return parsed.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

export default function BankDetailsPage() {
  const [accountsData, setAccountsData] = useState<{
    accounts: BankDetailAccount[];
    totalBalance: string | null;
    missingBalanceAccountCount: number;
  }>({ accounts: [], totalBalance: null, missingBalanceAccountCount: 0 });
  const [selectedAccountKey, setSelectedAccountKey] = useState<string | null>(null);
  const [dateFilter, setDateFilter] = useState<BankDateFilter>(() => createDateFilter("current_month"));
  const [monthValue, setMonthValue] = useState("2026-05");
  const [rows, setRows] = useState<BankDetailTransaction[]>([]);
  const [loading, setLoading] = useState(true);
  const [rowLoading, setRowLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    fetchBankDetailAccounts(controller.signal)
      .then((payload) => {
        setAccountsData({
          accounts: payload.accounts,
          totalBalance: payload.totalBalance,
          missingBalanceAccountCount: payload.missingBalanceAccountCount,
        });
        setSelectedAccountKey((current) => current ?? payload.accounts[0]?.accountKey ?? null);
      })
      .catch((caught) => setError(caught instanceof Error ? caught.message : "银行明细加载失败。"))
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!selectedAccountKey) {
      setRows([]);
      return;
    }
    const controller = new AbortController();
    setRowLoading(true);
    fetchBankDetailTransactions({
      accountKey: selectedAccountKey,
      dateFrom: dateFilter.dateFrom,
      dateTo: dateFilter.dateTo,
      signal: controller.signal,
    })
      .then((payload) => setRows(payload.rows))
      .catch((caught) => setError(caught instanceof Error ? caught.message : "银行流水加载失败。"))
      .finally(() => setRowLoading(false));
    return () => controller.abort();
  }, [dateFilter.dateFrom, dateFilter.dateTo, selectedAccountKey]);

  const selectedAccount = useMemo(
    () => accountsData.accounts.find((account) => account.accountKey === selectedAccountKey) ?? null,
    [accountsData.accounts, selectedAccountKey],
  );

  const applyPreset = (preset: BankDateFilter["preset"]) => {
    setDateFilter(createDateFilter(preset, monthValue));
  };

  const handleMonthChange = (value: string) => {
    setMonthValue(value);
    if (value) {
      setDateFilter(createDateFilter("month", value));
    }
  };

  const handleCustomDateChange = (key: "dateFrom" | "dateTo", value: string) => {
    setDateFilter((current) => ({
      preset: "custom",
      dateFrom: key === "dateFrom" ? value : current.dateFrom,
      dateTo: key === "dateTo" ? value : current.dateTo,
    }));
  };

  return (
    <div className="bank-details-page" data-testid="bank-details-page">
      <header className="bank-details-header">
        <div>
          <div className="eyebrow">已导入流水</div>
          <h1>银行明细</h1>
        </div>
        <div className="bank-balance-summary">
          <div>
            <span>总余额</span>
            <strong>{displayBalance(accountsData.totalBalance)}</strong>
          </div>
          {accountsData.missingBalanceAccountCount > 0 ? <span>{accountsData.missingBalanceAccountCount} 个账户无余额</span> : null}
        </div>
      </header>

      {error ? <div className="state-panel error">{error}</div> : null}
      {loading ? <div className="state-panel">正在加载银行明细。</div> : null}
      {!loading && accountsData.accounts.length === 0 ? <div className="state-panel">暂无银行流水，请先在导入中心导入银行流水。</div> : null}

      <section className="bank-balance-strip" aria-label="账户余额">
        {accountsData.accounts.map((account) => (
          <div key={account.accountKey} aria-label={`${account.displayName} 余额`} className="bank-balance-chip">
            <span>{account.displayName}</span>
            <strong>{displayBalance(account.latestBalance)}</strong>
          </div>
        ))}
      </section>

      <div className="bank-details-layout">
        <aside className="bank-account-tree" aria-label="银行账户">
          {accountsData.accounts.map((account) => (
            <button
              key={account.accountKey}
              aria-current={account.accountKey === selectedAccountKey ? "true" : undefined}
              className={`bank-account-node${account.accountKey === selectedAccountKey ? " active" : ""}`}
              type="button"
              onClick={() => setSelectedAccountKey(account.accountKey)}
            >
              <span>{account.displayName}</span>
              <strong>{displayBalance(account.latestBalance)}</strong>
              <small>当前范围 {account.transactionCount} 条</small>
            </button>
          ))}
        </aside>

        <section className="bank-transaction-panel">
          <div className="bank-transaction-toolbar">
            <div>
              <h2>{selectedAccount?.displayName ?? "账户流水"}</h2>
              <p>{dateFilter.dateFrom} 至 {dateFilter.dateTo}</p>
            </div>
            <div className="bank-date-filter">
              <button type="button" onClick={() => applyPreset("current_month")}>本月</button>
              <button type="button" onClick={() => applyPreset("previous_month")}>上月</button>
              <button type="button" onClick={() => applyPreset("last_7_days")}>近7天</button>
              <button type="button" onClick={() => applyPreset("last_30_days")}>近30天</button>
              <button type="button" onClick={() => applyPreset("current_year")}>今年</button>
              <label>
                年月筛选
                <input aria-label="年月筛选" type="month" value={monthValue} onChange={(event) => handleMonthChange(event.target.value)} />
              </label>
              <label>
                开始日期
                <input aria-label="开始日期" type="date" value={dateFilter.dateFrom} onChange={(event) => handleCustomDateChange("dateFrom", event.target.value)} />
              </label>
              <label>
                结束日期
                <input aria-label="结束日期" type="date" value={dateFilter.dateTo} onChange={(event) => handleCustomDateChange("dateTo", event.target.value)} />
              </label>
            </div>
          </div>

          {rowLoading ? <div className="state-panel">正在加载流水。</div> : null}
          {!rowLoading && rows.length === 0 ? <div className="state-panel">当前时间范围内没有流水。</div> : null}
          {rows.length > 0 ? (
            <table className="bank-transaction-table">
              <thead>
                <tr>
                  <th>交易时间</th>
                  <th>对方户名</th>
                  <th>金额</th>
                  <th>余额</th>
                  <th>摘要</th>
                  <th>用途</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.id}>
                    <td>{row.tradeTime}</td>
                    <td>{row.counterpartyName}</td>
                    <td><span className={`direction-tag ${row.direction}`}>{row.directionLabel}</span> {formatMoney(row.amount)}</td>
                    <td>{formatMoney(row.balance)}</td>
                    <td>{row.summary}</td>
                    <td>{row.purpose}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : null}
        </section>
      </div>
    </div>
  );
}
