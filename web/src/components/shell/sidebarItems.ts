import AccountBalanceOutlinedIcon from "@mui/icons-material/AccountBalanceOutlined";
import AssessmentOutlinedIcon from "@mui/icons-material/AssessmentOutlined";
import CalculateOutlinedIcon from "@mui/icons-material/CalculateOutlined";
import DirectionsCarFilledOutlinedIcon from "@mui/icons-material/DirectionsCarFilledOutlined";
import HubOutlinedIcon from "@mui/icons-material/HubOutlined";
import ReceiptLongOutlinedIcon from "@mui/icons-material/ReceiptLongOutlined";
import SettingsOutlinedIcon from "@mui/icons-material/SettingsOutlined";
import UploadFileOutlinedIcon from "@mui/icons-material/UploadFileOutlined";
import type { SvgIconComponent } from "@mui/icons-material";

export type SidebarItem = {
  label: string;
  to: string;
  icon: SvgIconComponent;
  end?: boolean;
};

export type SidebarGroup = {
  title: string;
  items: SidebarItem[];
};

export const sidebarGroups: SidebarGroup[] = [
  {
    title: "系统操作",
    items: [
      { label: "设置", to: "/settings", icon: SettingsOutlinedIcon },
      { label: "导入中心", to: "/imports", icon: UploadFileOutlinedIcon },
      { label: "银行流水导入", to: "/imports?intent=bank_transaction", icon: AccountBalanceOutlinedIcon },
      { label: "发票导入", to: "/imports?intent=invoice", icon: ReceiptLongOutlinedIcon },
      { label: "ETC发票导入", to: "/imports?intent=etc_invoice", icon: DirectionsCarFilledOutlinedIcon },
    ],
  },
  {
    title: "财务业务",
    items: [
      { label: "关联台", to: "/", icon: HubOutlinedIcon, end: true },
      { label: "税金抵扣", to: "/tax-offset", icon: CalculateOutlinedIcon },
      { label: "成本统计", to: "/cost-statistics", icon: AssessmentOutlinedIcon },
      { label: "银行明细", to: "/bank-details", icon: AccountBalanceOutlinedIcon },
      { label: "ETC票据管理", to: "/etc-tickets", icon: DirectionsCarFilledOutlinedIcon },
    ],
  },
];
