import { describe, expect, test } from "vitest";
import { buildCategoryGroups, categoryCodesForSelection } from "../features/bankFlowRuleBatches/viewModel";
import type { BankFlowRuleBatchSummary, BankFlowRuleBatchSummaryCategory, BankFlowRuleLabelCount } from "../features/bankFlowRuleBatches/types";

function category(code: string, primaryLabel: string, subLabel: string): BankFlowRuleBatchSummaryCategory {
  return { code, label: subLabel || primaryLabel, primaryLabel, subLabel, total: 3, draft: 1, submitted: 1, withdrawn: 1,
    conflict: 0, stale: 0, totalRowCount: 999, draftRowCount: 999, submittedRowCount: 999, withdrawnRowCount: 999, totalAmount: "1.00" };
}
function count(primaryLabel: string, subLabel: string | null, draft: number): BankFlowRuleLabelCount {
  return { primaryLabel, subLabel, draftRowCount: draft, submittedRowCount: draft * 2, withdrawnRowCount: draft * 3, totalRowCount: draft * 6 };
}
function summary(categories: BankFlowRuleBatchSummaryCategory[], labelCounts: BankFlowRuleLabelCount[]): BankFlowRuleBatchSummary {
  return { categories, labelCounts, draftCount: 1, submittedCount: 1, withdrawnCount: 1, conflictCount: 0, staleCount: 0,
    totalRowCount: 600, draftRowCount: 100, submittedRowCount: 200, withdrawnRowCount: 300, totalAmount: "1.00" };
}

describe("batch category navigation contract", () => {
  const data = summary([
    category("salary", "薪资社保福利", "工资"), category("salary_extra", "薪资社保福利", "工资"),
    category("bonus", "薪资社保福利", "奖金"), category("direct", "薪资社保福利", ""),
  ], [count("薪资社保福利", null, 12), count("薪资社保福利", "工资", 8), count("薪资社保福利", "奖金", 3), count("薪资社保福利", "", 1)]);

  test("counts distinct real children, keeps direct-parent flows and reads full-range row counts", () => {
    const [group] = buildCategoryGroups(data, "unsubmitted");
    expect(group.childCount).toBe(2);
    expect(group.rowCount).toBe(12);
    expect(group.codes).toEqual(["salary", "salary_extra", "bonus", "direct"]);
    expect(group.children).toEqual([
      { key: "工资", label: "工资", codes: ["salary", "salary_extra"], rowCount: 8 },
      { key: "奖金", label: "奖金", codes: ["bonus"], rowCount: 3 },
      { key: "", label: "主标签本身", codes: ["direct"], rowCount: 1 },
    ]);
  });

  test.each([["submitted", 24, 16], ["withdrawn", 36, 24], ["all", 72, 48]] as const)("uses %s counts", (bucket, parent, child) => {
    const [group] = buildCategoryGroups(data, bucket);
    expect(group.rowCount).toBe(parent);
    expect(group.children[0].rowCount).toBe(child);
  });

  test("resolves parent, child, direct-parent and overview scopes without auto-selecting a child", () => {
    const groups = buildCategoryGroups(data, "unsubmitted");
    expect(categoryCodesForSelection(groups, "", null)).toEqual([]);
    expect(categoryCodesForSelection(groups, "薪资社保福利", null)).toEqual(["salary", "salary_extra", "bonus", "direct"]);
    expect(categoryCodesForSelection(groups, "薪资社保福利", "工资")).toEqual(["salary", "salary_extra"]);
    expect(categoryCodesForSelection(groups, "薪资社保福利", "")).toEqual(["direct"]);
    expect(categoryCodesForSelection(groups, "已删除", null)).toBeNull();
    expect(categoryCodesForSelection(groups, "薪资社保福利", "已删除")).toBeNull();
  });

  test("does not include categories outside the current bucket or duplicate rule codes", () => {
    const categories = [...data.categories, data.categories[0], { ...category("hidden", "其他", "其他"), draft: 0 }];
    expect(buildCategoryGroups({ ...data, categories }, "unsubmitted")).toEqual(buildCategoryGroups(data, "unsubmitted"));
    expect(buildCategoryGroups(summary([], []), "unsubmitted")).toEqual([]);
  });

  test("a group with only direct-parent flows has zero real children", () => {
    const [group] = buildCategoryGroups(summary([category("direct", "往来", "")], [count("往来", null, 4), count("往来", "", 4)]), "unsubmitted");
    expect(group.childCount).toBe(0);
    expect(group.children[0].rowCount).toBe(4);
  });

  test("fails explicitly on missing authoritative statistics instead of manufacturing zero", () => {
    expect(() => buildCategoryGroups({ ...data, labelCounts: [] }, "unsubmitted")).toThrow("流水分类统计缺失。");
    expect(() => buildCategoryGroups({ ...data, labelCounts: data.labelCounts.filter((item) => item.subLabel !== "工资") }, "unsubmitted")).toThrow("流水分类统计缺失。");
  });
});
