import AccountBalanceOutlinedIcon from "@mui/icons-material/AccountBalanceOutlined";
import AssessmentOutlinedIcon from "@mui/icons-material/AssessmentOutlined";
import CalculateOutlinedIcon from "@mui/icons-material/CalculateOutlined";
import DirectionsCarFilledOutlinedIcon from "@mui/icons-material/DirectionsCarFilledOutlined";
import HubOutlinedIcon from "@mui/icons-material/HubOutlined";
import ReceiptLongOutlinedIcon from "@mui/icons-material/ReceiptLongOutlined";
import SearchOutlinedIcon from "@mui/icons-material/SearchOutlined";
import SettingsOutlinedIcon from "@mui/icons-material/SettingsOutlined";
import type { SvgIconComponent } from "@mui/icons-material";
import type { WorkbenchRouteState } from "../../contexts/AppChromeContext";

export type SidebarItem = {
  id?: string;
  label: string;
  to: string;
  icon: SvgIconComponent;
  end?: boolean;
  active?: boolean;
  state?: WorkbenchRouteState;
};

export type SidebarGroup = {
  title: string;
  items: SidebarItem[];
};

export const sidebarGroups: SidebarGroup[] = [
  {
    title: "财务业务",
    items: [
      { label: "关联台", to: "/", icon: HubOutlinedIcon, end: true },
      {
        id: "workbench-search",
        label: "关联台搜索",
        to: "/",
        icon: SearchOutlinedIcon,
        active: false,
        state: { workbenchHeaderIntent: { type: "open_search" } },
      },
      { label: "税金抵扣", to: "/tax-offset", icon: CalculateOutlinedIcon },
      { label: "成本统计", to: "/cost-statistics", icon: AssessmentOutlinedIcon },
      { label: "银行明细", to: "/bank-details", icon: AccountBalanceOutlinedIcon },
      { label: "ETC票据管理", to: "/etc-tickets", icon: DirectionsCarFilledOutlinedIcon },
    ],
  },
  {
    title: "系统操作",
    items: [
      { label: "设置", to: "/settings", icon: SettingsOutlinedIcon },
      {
        id: "workbench-bank-import",
        label: "银行流水导入",
        to: "/imports/bank-transactions",
        icon: AccountBalanceOutlinedIcon,
        active: false,
      },
      {
        id: "workbench-invoice-import",
        label: "发票导入",
        to: "/imports/invoices",
        icon: ReceiptLongOutlinedIcon,
        active: false,
      },
      {
        id: "workbench-etc-import",
        label: "ETC发票导入",
        to: "/imports/etc-invoices",
        icon: DirectionsCarFilledOutlinedIcon,
        active: false,
      },
    ],
  },
];
