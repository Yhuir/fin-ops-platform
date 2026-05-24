import { Navigate, Route, Routes } from "react-router-dom";

import ReconciliationWorkbenchPage from "../pages/ReconciliationWorkbenchPage";
import TaxOffsetPage from "../pages/TaxOffsetPage";
import CostStatisticsPage from "../pages/CostStatisticsPage";
import SettingsPage from "../pages/SettingsPage";
import AppHealthOperationsPage from "../pages/AppHealthOperationsPage";
import BatchAccountingPage from "../pages/BatchAccountingPage";
import BankDetailsPage from "../pages/BankDetailsPage";
import PendingInvoicesPage from "../pages/PendingInvoicesPage";
import EtcTicketManagementPage from "../pages/EtcTicketManagementPage";
import NoOaBankBatchPage from "../pages/NoOaBankBatchPage";
import TurnoverLedgerPage from "../pages/TurnoverLedgerPage";
import InputInvoiceUsagePage from "../pages/InputInvoiceUsagePage";
import OutputInvoiceCollectionsPage from "../pages/OutputInvoiceCollectionsPage";
import ImportBankTransactionsPage from "../pages/imports/ImportBankTransactionsPage";
import ImportInvoicesPage from "../pages/imports/ImportInvoicesPage";
import ImportEtcInvoicesPage from "../pages/imports/ImportEtcInvoicesPage";

export default function AppRouter() {
  return (
    <Routes>
      <Route path="/" element={<ReconciliationWorkbenchPage />} />
      <Route path="/imports/bank-transactions" element={<ImportBankTransactionsPage />} />
      <Route path="/imports/invoices" element={<ImportInvoicesPage />} />
      <Route path="/imports/etc-invoices" element={<ImportEtcInvoicesPage />} />
      <Route path="/tax-offset" element={<TaxOffsetPage />} />
      <Route path="/cost-statistics" element={<CostStatisticsPage />} />
      <Route path="/bank-details" element={<BankDetailsPage />} />
      <Route path="/pending-invoices" element={<PendingInvoicesPage />} />
      <Route path="/input-invoice-usage" element={<InputInvoiceUsagePage />} />
      <Route path="/output-invoice-collections" element={<OutputInvoiceCollectionsPage />} />
      <Route path="/no-oa-bank-batches" element={<NoOaBankBatchPage />} />
      <Route path="/batch-accounting" element={<BatchAccountingPage />} />
      <Route path="/turnover-ledger" element={<TurnoverLedgerPage />} />
      <Route path="/etc-tickets" element={<EtcTicketManagementPage />} />
      <Route path="/settings" element={<SettingsPage />} />
      <Route path="/operations/app-health" element={<AppHealthOperationsPage />} />
      <Route path="*" element={<Navigate replace to="/" />} />
    </Routes>
  );
}
