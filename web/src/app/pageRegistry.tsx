import AccountBalanceWalletOutlinedIcon from "@mui/icons-material/AccountBalanceWalletOutlined";
import AccountBalanceOutlinedIcon from "@mui/icons-material/AccountBalanceOutlined";
import AssessmentOutlinedIcon from "@mui/icons-material/AssessmentOutlined";
import AssignmentLateOutlinedIcon from "@mui/icons-material/AssignmentLateOutlined";
import CalculateOutlinedIcon from "@mui/icons-material/CalculateOutlined";
import DescriptionOutlinedIcon from "@mui/icons-material/DescriptionOutlined";
import DirectionsCarFilledOutlinedIcon from "@mui/icons-material/DirectionsCarFilledOutlined";
import FactCheckOutlinedIcon from "@mui/icons-material/FactCheckOutlined";
import HandshakeOutlinedIcon from "@mui/icons-material/HandshakeOutlined";
import HubOutlinedIcon from "@mui/icons-material/HubOutlined";
import InputOutlinedIcon from "@mui/icons-material/InputOutlined";
import MonitorHeartOutlinedIcon from "@mui/icons-material/MonitorHeartOutlined";
import MoveToInboxOutlinedIcon from "@mui/icons-material/MoveToInboxOutlined";
import OutputOutlinedIcon from "@mui/icons-material/OutputOutlined";
import PlaylistAddCheckOutlinedIcon from "@mui/icons-material/PlaylistAddCheckOutlined";
import SettingsOutlinedIcon from "@mui/icons-material/SettingsOutlined";
import TollOutlinedIcon from "@mui/icons-material/TollOutlined";
import type { SvgIconComponent } from "@mui/icons-material";
import type { ComponentType } from "react";

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
import OaPendingPaymentsPage from "../pages/OaPendingPaymentsPage";
import OutputInvoiceCollectionsPage from "../pages/OutputInvoiceCollectionsPage";
import ImportBankTransactionsPage from "../pages/imports/ImportBankTransactionsPage";
import ImportInvoicesPage from "../pages/imports/ImportInvoicesPage";
import ImportEtcInvoicesPage from "../pages/imports/ImportEtcInvoicesPage";

export type AppPageRoute = {
  path: string;
  pageKey: string;
  component: ComponentType;
  keepAlive: boolean;
  sessionVersion: number;
  maxIdleMs?: number;
  end?: boolean;
};

export type SidebarItem = {
  id?: string;
  label: string;
  to: string;
  icon: SvgIconComponent;
  end?: boolean;
  active?: boolean;
};

export type SidebarGroup = {
  title: string;
  items: SidebarItem[];
};

type AppPageDefinition = AppPageRoute & {
  sidebar?: {
    group: "finance" | "system";
    label: string;
    icon: SvgIconComponent;
    id?: string;
    active?: boolean;
  };
};

const DEFAULT_PAGE_MAX_IDLE_MS = 30 * 60 * 1000;

export const appPageDefinitions: AppPageDefinition[] = [
  {
    path: "/",
    pageKey: "reconciliation-workbench",
    component: ReconciliationWorkbenchPage,
    keepAlive: true,
    sessionVersion: 1,
    maxIdleMs: DEFAULT_PAGE_MAX_IDLE_MS,
    end: true,
    sidebar: { group: "finance", label: "关联台", icon: HubOutlinedIcon },
  },
  {
    path: "/tax-offset",
    pageKey: "tax-offset",
    component: TaxOffsetPage,
    keepAlive: true,
    sessionVersion: 1,
    maxIdleMs: DEFAULT_PAGE_MAX_IDLE_MS,
    sidebar: { group: "finance", label: "税金抵扣", icon: CalculateOutlinedIcon },
  },
  {
    path: "/cost-statistics",
    pageKey: "cost-statistics",
    component: CostStatisticsPage,
    keepAlive: true,
    sessionVersion: 1,
    maxIdleMs: DEFAULT_PAGE_MAX_IDLE_MS,
    sidebar: { group: "finance", label: "成本统计", icon: AssessmentOutlinedIcon },
  },
  {
    path: "/bank-details",
    pageKey: "bank-details",
    component: BankDetailsPage,
    keepAlive: true,
    sessionVersion: 1,
    maxIdleMs: DEFAULT_PAGE_MAX_IDLE_MS,
    sidebar: { group: "finance", label: "银行明细", icon: AccountBalanceOutlinedIcon },
  },
  {
    path: "/pending-invoices",
    pageKey: "pending-invoices",
    component: PendingInvoicesPage,
    keepAlive: true,
    sessionVersion: 1,
    maxIdleMs: DEFAULT_PAGE_MAX_IDLE_MS,
    sidebar: { group: "finance", label: "待找发票", icon: AssignmentLateOutlinedIcon },
  },
  {
    path: "/input-invoice-usage",
    pageKey: "input-invoice-usage",
    component: InputInvoiceUsagePage,
    keepAlive: true,
    sessionVersion: 1,
    maxIdleMs: DEFAULT_PAGE_MAX_IDLE_MS,
    sidebar: { group: "finance", label: "进项发票使用情况", icon: InputOutlinedIcon },
  },
  {
    path: "/oa-pending-payments",
    pageKey: "oa-pending-payments",
    component: OaPendingPaymentsPage,
    keepAlive: true,
    sessionVersion: 1,
    maxIdleMs: DEFAULT_PAGE_MAX_IDLE_MS,
    sidebar: { group: "finance", label: "OA待付款核对", icon: FactCheckOutlinedIcon },
  },
  {
    path: "/output-invoice-collections",
    pageKey: "output-invoice-collections",
    component: OutputInvoiceCollectionsPage,
    keepAlive: true,
    sessionVersion: 1,
    maxIdleMs: DEFAULT_PAGE_MAX_IDLE_MS,
    sidebar: { group: "finance", label: "销项发票收款情况", icon: OutputOutlinedIcon },
  },
  {
    path: "/no-oa-bank-batches",
    pageKey: "no-oa-bank-batches",
    component: NoOaBankBatchPage,
    keepAlive: true,
    sessionVersion: 1,
    maxIdleMs: DEFAULT_PAGE_MAX_IDLE_MS,
    sidebar: { group: "finance", label: "免OA流水批量处理", icon: PlaylistAddCheckOutlinedIcon },
  },
  {
    path: "/batch-accounting",
    pageKey: "batch-accounting",
    component: BatchAccountingPage,
    keepAlive: true,
    sessionVersion: 1,
    maxIdleMs: DEFAULT_PAGE_MAX_IDLE_MS,
    sidebar: { group: "finance", label: "批量账务", icon: AccountBalanceWalletOutlinedIcon },
  },
  {
    path: "/turnover-ledger",
    pageKey: "turnover-ledger",
    component: TurnoverLedgerPage,
    keepAlive: true,
    sessionVersion: 1,
    maxIdleMs: DEFAULT_PAGE_MAX_IDLE_MS,
    sidebar: { group: "finance", label: "外部往来款管理", icon: HandshakeOutlinedIcon },
  },
  {
    path: "/etc-tickets",
    pageKey: "etc-tickets",
    component: EtcTicketManagementPage,
    keepAlive: true,
    sessionVersion: 1,
    maxIdleMs: DEFAULT_PAGE_MAX_IDLE_MS,
    sidebar: { group: "finance", label: "ETC票据管理", icon: TollOutlinedIcon },
  },
  {
    path: "/settings",
    pageKey: "settings",
    component: SettingsPage,
    keepAlive: true,
    sessionVersion: 1,
    maxIdleMs: DEFAULT_PAGE_MAX_IDLE_MS,
    sidebar: { group: "system", label: "设置", icon: SettingsOutlinedIcon },
  },
  {
    path: "/operations/app-health",
    pageKey: "app-health-operations",
    component: AppHealthOperationsPage,
    keepAlive: true,
    sessionVersion: 1,
    maxIdleMs: DEFAULT_PAGE_MAX_IDLE_MS,
    sidebar: { group: "system", label: "系统状态", icon: MonitorHeartOutlinedIcon },
  },
  {
    path: "/imports/bank-transactions",
    pageKey: "imports.bank-transactions",
    component: ImportBankTransactionsPage,
    keepAlive: true,
    sessionVersion: 1,
    maxIdleMs: DEFAULT_PAGE_MAX_IDLE_MS,
    sidebar: {
      group: "system",
      id: "workbench-bank-import",
      label: "银行流水导入",
      icon: MoveToInboxOutlinedIcon,
      active: false,
    },
  },
  {
    path: "/imports/invoices",
    pageKey: "imports.invoices",
    component: ImportInvoicesPage,
    keepAlive: true,
    sessionVersion: 1,
    maxIdleMs: DEFAULT_PAGE_MAX_IDLE_MS,
    sidebar: {
      group: "system",
      id: "workbench-invoice-import",
      label: "发票导入",
      icon: DescriptionOutlinedIcon,
      active: false,
    },
  },
  {
    path: "/imports/etc-invoices",
    pageKey: "imports.etc-invoices",
    component: ImportEtcInvoicesPage,
    keepAlive: true,
    sessionVersion: 1,
    maxIdleMs: DEFAULT_PAGE_MAX_IDLE_MS,
    sidebar: {
      group: "system",
      id: "workbench-etc-import",
      label: "ETC发票导入",
      icon: DirectionsCarFilledOutlinedIcon,
      active: false,
    },
  },
];

export const appPageRoutes: AppPageRoute[] = appPageDefinitions.map((definition) => ({
  path: definition.path,
  pageKey: definition.pageKey,
  component: definition.component,
  keepAlive: definition.keepAlive,
  sessionVersion: definition.sessionVersion,
  maxIdleMs: definition.maxIdleMs,
  end: definition.end,
}));

function sidebarItemFromDefinition(definition: AppPageDefinition): SidebarItem | null {
  if (!definition.sidebar) {
    return null;
  }
  return {
    id: definition.sidebar.id,
    label: definition.sidebar.label,
    to: definition.path,
    icon: definition.sidebar.icon,
    end: definition.end,
    active: definition.sidebar.active,
  };
}

export const sidebarGroups: SidebarGroup[] = [
  {
    title: "财务业务",
    items: appPageDefinitions
      .filter((definition) => definition.sidebar?.group === "finance")
      .map(sidebarItemFromDefinition)
      .filter((item): item is SidebarItem => item !== null),
  },
  {
    title: "系统操作",
    items: appPageDefinitions
      .filter((definition) => definition.sidebar?.group === "system")
      .map(sidebarItemFromDefinition)
      .filter((item): item is SidebarItem => item !== null),
  },
];
