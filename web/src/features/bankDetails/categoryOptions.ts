import type { BankTransactionCategoryCode, BankTransactionCategoryCounts } from "./types";

export type BankTransactionCategoryOption = {
  code: BankTransactionCategoryCode;
  root: string;
  group: string;
  status: string;
  label: string;
  menuLabel: string;
};

export const CATEGORY_TREE: Array<{
  root: string;
  groups: Array<{
    name: string;
    displayName: string;
    items: Array<{ code: BankTransactionCategoryCode; status: string; label?: string; menuLabel?: string }>;
  }>;
}> = [
  {
    root: "借入",
    groups: [
      {
        name: "个人往来款",
        displayName: "个人暂借款",
        items: [
          { code: "borrow_in_personal_pending_repayment", status: "待还款" },
          { code: "borrow_in_personal_repaid", status: "已还款" },
        ],
      },
      {
        name: "公司往来款",
        displayName: "公司暂借款",
        items: [
          { code: "borrow_in_company_pending_repayment", status: "待还款" },
          { code: "borrow_in_company_repaid", status: "已还款" },
        ],
      },
      {
        name: "银行往来款",
        displayName: "银行往来款",
        items: [
          { code: "borrow_in_bank_pending_repayment", status: "待还款" },
          { code: "borrow_in_bank_repaid", status: "已还款" },
        ],
      },
    ],
  },
  {
    root: "借出",
    groups: [
      {
        name: "个人往来款",
        displayName: "个人往来款",
        items: [
          { code: "borrow_out_personal_lent", status: "待收款" },
          { code: "borrow_out_personal_pending_collection", status: "已收款" },
        ],
      },
      {
        name: "公司往来款",
        displayName: "公司往来款",
        items: [
          { code: "borrow_out_company_lent", status: "待收款" },
          { code: "borrow_out_company_pending_collection", status: "已收款" },
        ],
      },
      {
        name: "银行往来款",
        displayName: "银行往来款",
        items: [
          { code: "borrow_out_bank_lent", status: "待收款" },
          { code: "borrow_out_bank_pending_collection", status: "已收款" },
        ],
      },
      {
        name: "货款往来款",
        displayName: "货款往来款",
        items: [
          { code: "borrow_out_goods_lent", status: "待收款" },
          { code: "borrow_out_goods_pending_collection", status: "已收款" },
        ],
      },
    ],
  },
  {
    root: "业务往来",
    groups: [
      {
        name: "质保金",
        displayName: "质保金",
        items: [{ code: "business_warranty_pending_collection", status: "待收款" }],
      },
      {
        name: "投标保证金",
        displayName: "投标保证金",
        items: [{ code: "business_bid_bond_pending_collection", status: "待收款" }],
      },
      {
        name: "履约保证金",
        displayName: "履约保证金",
        items: [{ code: "business_performance_bond_pending_collection", status: "待收款" }],
      },
      {
        name: "已开发票未收款",
        displayName: "已开发票未收款",
        items: [{ code: "business_invoiced_pending_collection", status: "待收款" }],
      },
    ],
  },
  {
    root: "自动识别",
    groups: [
      {
        name: "常用分类",
        displayName: "自动识别",
        items: [
          { code: "fee", status: "手续费", label: "手续费", menuLabel: "自动识别 / 手续费" },
          { code: "salary", status: "工资", label: "工资", menuLabel: "自动识别 / 工资" },
          { code: "holiday_bonus", status: "过节费", label: "过节费", menuLabel: "自动识别 / 过节费" },
          { code: "bonus", status: "奖金", label: "奖金", menuLabel: "自动识别 / 奖金" },
          { code: "tax_payment", status: "税款", label: "税款", menuLabel: "自动识别 / 税款" },
          {
            code: "treasury_tax_collection",
            status: "代理国库税收收缴",
            label: "代理国库税收收缴",
            menuLabel: "自动识别 / 代理国库税收收缴",
          },
          { code: "social_security", status: "社保款", label: "社保款", menuLabel: "自动识别 / 社保款" },
          { code: "internal_transfer", status: "内部往来款", label: "内部往来款", menuLabel: "自动识别 / 内部往来款" },
        ],
      },
    ],
  },
];

export const SELECTABLE_CATEGORY_OPTIONS: BankTransactionCategoryOption[] = CATEGORY_TREE.flatMap((rootNode) => (
  rootNode.groups.flatMap((group) => (
    group.items.map((item) => ({
      code: item.code,
      root: rootNode.root,
      group: group.name,
      status: item.status,
      label: item.label ?? `${group.displayName}：${item.status}`,
      menuLabel: item.menuLabel ?? `${rootNode.root} / ${group.name} / ${item.status}`,
    }))
  ))
));

export const CATEGORY_LABEL_BY_CODE: Partial<Record<BankTransactionCategoryCode, string>> = {
  ...Object.fromEntries(SELECTABLE_CATEGORY_OPTIONS.map((option) => [option.code, option.label])),
  external_turnover: "外部往来款",
  internal_transfer: "内部往来款",
  offset: "冲",
  cash_turnover: "现金往来",
};

export const EMPTY_CATEGORY_COUNTS: BankTransactionCategoryCounts = {
  uncategorized: 0,
  ...Object.fromEntries(SELECTABLE_CATEGORY_OPTIONS.map((option) => [option.code, 0])),
};

export function getBankCategoryToneClass(categoryCode: BankTransactionCategoryCode | null) {
  if (!categoryCode) {
    return "category-tone-empty";
  }
  if (categoryCode.startsWith("borrow_in_")) {
    return "category-tone-borrow-in";
  }
  if (categoryCode.startsWith("borrow_out_")) {
    return "category-tone-borrow-out";
  }
  if (categoryCode === "fee") {
    return "category-tone-fee";
  }
  if (categoryCode === "salary") {
    return "category-tone-salary";
  }
  if (categoryCode === "internal_transfer") {
    return "category-tone-internal-transfer";
  }
  if (categoryCode === "holiday_bonus") {
    return "category-tone-holiday-bonus";
  }
  if (categoryCode === "bonus") {
    return "category-tone-bonus";
  }
  if (categoryCode === "tax_payment" || categoryCode === "treasury_tax_collection") {
    return "category-tone-tax";
  }
  if (categoryCode === "social_security") {
    return "category-tone-social-security";
  }
  if (categoryCode.startsWith("business_")) {
    return "category-tone-business";
  }
  return "category-tone-default";
}

export function splitBankCategoryLabel(label: string) {
  const separatorIndex = label.indexOf("：");
  if (separatorIndex <= 0 || separatorIndex >= label.length - 1) {
    return [label];
  }
  return [`${label.slice(0, separatorIndex)}：`, label.slice(separatorIndex + 1)];
}
