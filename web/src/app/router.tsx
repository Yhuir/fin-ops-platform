import { Navigate, Route, Routes } from "react-router-dom";

import ReconciliationWorkbenchPage from "../pages/ReconciliationWorkbenchPage";
import TaxOffsetPage from "../pages/TaxOffsetPage";
import CostStatisticsPage from "../pages/CostStatisticsPage";
import SettingsPage from "../pages/SettingsPage";
import BankDetailsPage from "../pages/BankDetailsPage";
import EtcTicketManagementPage from "../pages/EtcTicketManagementPage";
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
      <Route path="/etc-tickets" element={<EtcTicketManagementPage />} />
      <Route path="/settings" element={<SettingsPage />} />
      <Route path="*" element={<Navigate replace to="/" />} />
    </Routes>
  );
}
