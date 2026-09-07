import { Navigate, useSearchParams } from "react-router-dom";
import CashBooks from "../components/cash/CashBooks";
import CashTasks from "../components/cash/CashTasks";
import CashSettings from "../components/cash/CashSettings";
import { CashNotice } from "../components/cash/CashUi";
import PageScaffold from "../components/common/PageScaffold";
import { CashProvider } from "../features/cash/hooks";
import "../components/cash/cash.css";

export default function CashPage() {
  const [params] = useSearchParams();
  const sections = params.getAll("section");
  if (sections.length === 0 && params.size === 0) return <Navigate to="/cash?section=accounts" replace />;
  if (sections.length !== 1 || params.size !== 1 || !["accounts", "tasks", "settings"].includes(sections[0])) {
    return <PageScaffold title="现金账" className="cash-page"><CashNotice error="现金页面地址不正确，请从左侧现金账子菜单进入。" /></PageScaffold>;
  }
  const section = sections[0];
  return <CashProvider><PageScaffold title={{ accounts: "现金账目", tasks: "每月任务", settings: "基础设置" }[section]!}
    titleAccessory={<span className="cash-breadcrumb">现金账</span>} className="cash-page">
    <div className="cash-view">{section === "accounts" ? <CashBooks /> : section === "tasks" ? <CashTasks /> : <CashSettings />}</div>
  </PageScaffold></CashProvider>;
}
