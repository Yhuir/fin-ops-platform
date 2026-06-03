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

export const sidebarGroups: SidebarGroup[] = [
  {
    title: "财务业务",
    items: [
      { label: "关联台", to: "/", icon: HubOutlinedIcon, end: true },
      { label: "税金抵扣", to: "/tax-offset", icon: CalculateOutlinedIcon },
      { label: "成本统计", to: "/cost-statistics", icon: AssessmentOutlinedIcon },
      { label: "银行明细", to: "/bank-details", icon: AccountBalanceOutlinedIcon },
      { label: "待找发票", to: "/pending-invoices", icon: AssignmentLateOutlinedIcon },
      { label: "进项发票使用情况", to: "/input-invoice-usage", icon: InputOutlinedIcon },
      { label: "OA待付款核对", to: "/oa-pending-payments", icon: FactCheckOutlinedIcon },
      { label: "销项发票收款情况", to: "/output-invoice-collections", icon: OutputOutlinedIcon },
      { label: "免OA流水批量处理", to: "/no-oa-bank-batches", icon: PlaylistAddCheckOutlinedIcon },
      { label: "批量账务", to: "/batch-accounting", icon: AccountBalanceWalletOutlinedIcon },
      { label: "外部往来款管理", to: "/turnover-ledger", icon: HandshakeOutlinedIcon },
      { label: "ETC票据管理", to: "/etc-tickets", icon: TollOutlinedIcon },
    ],
  },
  {
    title: "系统操作",
    items: [
      { label: "设置", to: "/settings", icon: SettingsOutlinedIcon },
      { label: "系统状态", to: "/operations/app-health", icon: MonitorHeartOutlinedIcon },
      {
        id: "workbench-bank-import",
        label: "银行流水导入",
        to: "/imports/bank-transactions",
        icon: MoveToInboxOutlinedIcon,
        active: false,
      },
      {
        id: "workbench-invoice-import",
        label: "发票导入",
        to: "/imports/invoices",
        icon: DescriptionOutlinedIcon,
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
