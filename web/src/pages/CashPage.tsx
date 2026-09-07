import { Navigate, useSearchParams } from "react-router-dom";
import { useState } from "react";
import CashBooks, { initialCashBooksCriteria } from "../components/cash/CashBooks";
import CashFlows from "../components/cash/CashFlows";
import { initialCashFlowCriteria } from "../components/cash/CashFlowTable";
import CashTasks, { initialCashTasksCriteria } from "../components/cash/CashTasks";
import CashSettings, { initialCashSettingsCriteria } from "../components/cash/CashSettings";
import { CashNotice } from "../components/cash/CashUi";
import PageScaffold from "../components/common/PageScaffold";
import { CashProvider } from "../features/cash/hooks";
import "../components/cash/cash.css";

export default function CashPage() {
  const [params] = useSearchParams();
  const sections = params.getAll("section");
  if (sections.length === 0 && params.size === 0) return <Navigate to="/cash?section=accounts" replace />;
  if (sections.length !== 1 || params.size !== 1 || !["flows", "accounts", "tasks", "settings"].includes(sections[0])) {
    return <PageScaffold title="现金账" className="cash-page"><CashNotice error="现金页面地址不正确，请从左侧现金账子菜单进入。" /></PageScaffold>;
  }
  return <div className="cash-workspace"><CashProvider><CashContent section={sections[0]} /></CashProvider></div>;
}

/** Only applied conditions survive a view switch. Denial unmounts this owner. */
function CashContent({ section }: { section: string }) {
  const [books, setBooks] = useState(initialCashBooksCriteria);
  const [flows, setFlows] = useState(initialCashFlowCriteria);
  const [tasks, setTasks] = useState(initialCashTasksCriteria);
  const [settings, setSettings] = useState(initialCashSettingsCriteria);
  return <PageScaffold title="现金账"
    titleAccessory={<span className="cash-breadcrumb">{{ flows: "现金流水", accounts: "现金账目", tasks: "每月任务", settings: "基础设置" }[section]}</span>} className="cash-page">
    <div className={`cash-view cash-view--${section}`}>
      {section === "flows" ? <CashFlows initialCriteria={flows} onCriteriaChange={setFlows} /> :
        section === "accounts" ? <CashBooks initialCriteria={books} onCriteriaChange={setBooks} /> :
          section === "tasks" ? <CashTasks initialCriteria={tasks} onCriteriaChange={setTasks} /> : <CashSettings initialCriteria={settings} onCriteriaChange={setSettings} />}
    </div>
  </PageScaffold>;
}
