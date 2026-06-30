import {
  Activity,
  Calculator,
  Car,
  ChartColumn,
  ClipboardCheck,
  FileInput,
  FileOutput,
  FileQuestion,
  FileText,
  Handshake,
  Inbox,
  Landmark,
  ListChecks,
  Network,
  Settings,
  Ticket,
  WalletCards,
  type LucideIcon,
} from "lucide-react";
import { lazy, type ComponentType, type LazyExoticComponent } from "react";

type AppPageComponent = ComponentType | LazyExoticComponent<ComponentType>;
type PageModule = { default: ComponentType };
type PageModuleLoader = () => Promise<PageModule>;

export type AppPageRoute = {
  path: string;
  pageKey: string;
  component: AppPageComponent;
  preload: () => Promise<void>;
  end?: boolean;
};

export type SidebarItem = {
  id?: string;
  label: string;
  to: string;
  icon: LucideIcon;
  preload: () => Promise<void>;
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
    icon: LucideIcon;
    id?: string;
    active?: boolean;
  };
};

function lazyPage(loader: PageModuleLoader): { component: AppPageComponent; preload: () => Promise<void> } {
  const component = lazy(loader);
  return {
    component,
    preload: () => loader().then(() => undefined),
  };
}

const reconciliationWorkbenchPage = lazyPage(() => import("../pages/ReconciliationWorkbenchPage"));
const taxOffsetPage = lazyPage(() => import("../pages/TaxOffsetPage"));
const costStatisticsPage = lazyPage(() => import("../pages/CostStatisticsPage"));
const bankDetailsPage = lazyPage(() => import("../pages/BankDetailsPage"));
const pendingInvoicesPage = lazyPage(() => import("../pages/PendingInvoicesPage"));
const inputInvoiceUsagePage = lazyPage(() => import("../pages/InputInvoiceUsagePage"));
const oaPendingPaymentsPage = lazyPage(() => import("../pages/OaPendingPaymentsPage"));
const outputInvoiceCollectionsPage = lazyPage(() => import("../pages/OutputInvoiceCollectionsPage"));
const bankFlowRuleBatchPage = lazyPage(() => import("../pages/BankFlowRuleBatchPage"));
const batchAccountingPage = lazyPage(() => import("../pages/BatchAccountingPage"));
const turnoverLedgerPage = lazyPage(() => import("../pages/TurnoverLedgerPage"));
const etcTicketManagementPage = lazyPage(() => import("../pages/EtcTicketManagementPage"));
const settingsPage = lazyPage(() => import("../pages/SettingsPage"));
const appHealthOperationsPage = lazyPage(() => import("../pages/AppHealthOperationsPage"));
const importBankTransactionsPage = lazyPage(() => import("../pages/imports/ImportBankTransactionsPage"));
const importInvoicesPage = lazyPage(() => import("../pages/imports/ImportInvoicesPage"));
const importEtcInvoicesPage = lazyPage(() => import("../pages/imports/ImportEtcInvoicesPage"));

export const appPageDefinitions: AppPageDefinition[] = [
  {
    path: "/",
    pageKey: "reconciliation-workbench",
    component: reconciliationWorkbenchPage.component,
    preload: reconciliationWorkbenchPage.preload,
    end: true,
    sidebar: { group: "finance", label: "关联台", icon: Network },
  },
  {
    path: "/cost-statistics",
    pageKey: "cost-statistics",
    component: costStatisticsPage.component,
    preload: costStatisticsPage.preload,
    sidebar: { group: "finance", label: "成本统计", icon: ChartColumn },
  },
  {
    path: "/bank-details",
    pageKey: "bank-details",
    component: bankDetailsPage.component,
    preload: bankDetailsPage.preload,
    sidebar: { group: "finance", label: "银行明细", icon: Landmark },
  },
  {
    path: "/oa-pending-payments",
    pageKey: "oa-pending-payments",
    component: oaPendingPaymentsPage.component,
    preload: oaPendingPaymentsPage.preload,
    sidebar: { group: "finance", label: "OA待付款核对", icon: ClipboardCheck },
  },
  {
    path: "/bank-flow-rule-batches",
    pageKey: "bank-flow-rule-batches",
    component: bankFlowRuleBatchPage.component,
    preload: bankFlowRuleBatchPage.preload,
    sidebar: { group: "finance", label: "流水规则批量处理", icon: ListChecks },
  },
  {
    path: "/batch-accounting",
    pageKey: "batch-accounting",
    component: batchAccountingPage.component,
    preload: batchAccountingPage.preload,
    sidebar: { group: "finance", label: "批量账务", icon: WalletCards },
  },
  {
    path: "/turnover-ledger",
    pageKey: "turnover-ledger",
    component: turnoverLedgerPage.component,
    preload: turnoverLedgerPage.preload,
    sidebar: { group: "finance", label: "外部往来款管理", icon: Handshake },
  },
  {
    path: "/etc-tickets",
    pageKey: "etc-tickets",
    component: etcTicketManagementPage.component,
    preload: etcTicketManagementPage.preload,
    sidebar: { group: "finance", label: "ETC票据管理", icon: Ticket },
  },
  {
    path: "/tax-offset",
    pageKey: "tax-offset",
    component: taxOffsetPage.component,
    preload: taxOffsetPage.preload,
    sidebar: { group: "finance", label: "税金抵扣", icon: Calculator },
  },
  {
    path: "/pending-invoices",
    pageKey: "pending-invoices",
    component: pendingInvoicesPage.component,
    preload: pendingInvoicesPage.preload,
    sidebar: { group: "finance", label: "待找发票", icon: FileQuestion },
  },
  {
    path: "/input-invoice-usage",
    pageKey: "input-invoice-usage",
    component: inputInvoiceUsagePage.component,
    preload: inputInvoiceUsagePage.preload,
    sidebar: { group: "finance", label: "进项发票使用情况", icon: FileInput },
  },
  {
    path: "/output-invoice-collections",
    pageKey: "output-invoice-collections",
    component: outputInvoiceCollectionsPage.component,
    preload: outputInvoiceCollectionsPage.preload,
    sidebar: { group: "finance", label: "销项发票收款情况", icon: FileOutput },
  },
  {
    path: "/settings",
    pageKey: "settings",
    component: settingsPage.component,
    preload: settingsPage.preload,
    sidebar: { group: "system", label: "设置", icon: Settings },
  },
  {
    path: "/operations/app-health",
    pageKey: "app-health-operations",
    component: appHealthOperationsPage.component,
    preload: appHealthOperationsPage.preload,
    sidebar: { group: "system", label: "系统状态", icon: Activity },
  },
  {
    path: "/imports/bank-transactions",
    pageKey: "imports.bank-transactions",
    component: importBankTransactionsPage.component,
    preload: importBankTransactionsPage.preload,
    sidebar: {
      group: "system",
      id: "workbench-bank-import",
      label: "银行流水导入",
      icon: Inbox,
      active: false,
    },
  },
  {
    path: "/imports/invoices",
    pageKey: "imports.invoices",
    component: importInvoicesPage.component,
    preload: importInvoicesPage.preload,
    sidebar: {
      group: "system",
      id: "workbench-invoice-import",
      label: "发票导入",
      icon: FileText,
      active: false,
    },
  },
  {
    path: "/imports/etc-invoices",
    pageKey: "imports.etc-invoices",
    component: importEtcInvoicesPage.component,
    preload: importEtcInvoicesPage.preload,
    sidebar: {
      group: "system",
      id: "workbench-etc-import",
      label: "ETC发票导入",
      icon: Car,
      active: false,
    },
  },
];

export const appPageRoutes: AppPageRoute[] = appPageDefinitions.map((definition) => ({
  path: definition.path,
  pageKey: definition.pageKey,
  component: definition.component,
  preload: definition.preload,
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
    preload: definition.preload,
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
