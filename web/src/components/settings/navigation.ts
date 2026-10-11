import type { SettingsNavigationItem } from "./types";

/** 设置分类只定义展示顺序；权限仍由页面入口决定。 */
export function settingsNavigation(
  canViewSettings: boolean,
  canManageAccessControl: boolean,
  canViewBatchHistory: boolean,
): SettingsNavigationItem[] {
  return [
    ...(canViewSettings ? [
      { id: "bank_accounts" as const, label: "银行账户" },
      { id: "oa_retention" as const, label: "OA导入设置" },
    ] : []),
    ...(canViewSettings && canManageAccessControl ? [
      { id: "access_accounts" as const, label: "访问账户" },
    ] : []),
    ...(canViewBatchHistory ? [{ id: "batch-accounting" as const, label: "批量账务" }] : []),
    ...(canViewSettings && canManageAccessControl ? [{ id: "data_reset" as const, label: "数据重置" }] : []),
  ];
}
