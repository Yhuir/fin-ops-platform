import { Navigate, Route, Routes } from "react-router-dom";

import ImportCenterPage from "../pages/ImportCenterPage";
import ReconciliationWorkbenchPage from "../pages/ReconciliationWorkbenchPage";
import TaxOffsetPage from "../pages/TaxOffsetPage";
import CostStatisticsPage from "../pages/CostStatisticsPage";
import SettingsPage from "../pages/SettingsPage";
import BankDetailsPage from "../pages/BankDetailsPage";
import EtcTicketManagementPage from "../pages/EtcTicketManagementPage";

export default function AppRouter() {
  return (
    <Routes>
      <Route path="/" element={<ReconciliationWorkbenchPage />} />
      <Route path="/imports" element={<ImportCenterPage />} />
      <Route path="/tax-offset" element={<TaxOffsetPage />} />
      <Route path="/cost-statistics" element={<CostStatisticsPage />} />
      <Route path="/bank-details" element={<BankDetailsPage />} />
      <Route path="/etc-tickets" element={<EtcTicketManagementPage />} />
      <Route path="/settings" element={<SettingsPage />} />
      <Route path="*" element={<Navigate replace to="/" />} />
    </Routes>
  );
}
