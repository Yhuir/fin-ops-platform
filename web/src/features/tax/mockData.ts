export type TaxInvoiceRecord = {
  id: string;
  invoiceType: string;
  counterparty: string;
  issueDate: string;
  taxRate: string;
  amount: string;
  taxAmount: string;
};

export type TaxMonthData = {
  outputInvoices: TaxInvoiceRecord[];
  inputInvoices: TaxInvoiceRecord[];
};

export type TaxSummary = {
  outputTax: string;
  inputTax: string;
  deductibleTax: string;
  resultLabel: string;
  resultAmount: string;
};

const taxDataByMonth: Record<string, TaxMonthData> = {
  "2026-03": {
    outputInvoices: [
      {
        id: "OUT-202603-001",
        invoiceType: "数电专票",
        counterparty: "华东项目甲方",
        issueDate: "2026-03-25",
        taxRate: "13%",
        amount: "320,000.00",
        taxAmount: "41,600.00",
      },
    ],
    inputInvoices: [
      {
        id: "IN-202603-014",
        invoiceType: "数电专票",
        counterparty: "设备供应商",
        issueDate: "2026-03-22",
        taxRate: "13%",
        amount: "96,000.00",
        taxAmount: "12,480.00",
      },
      {
        id: "IN-202603-015",
        invoiceType: "数电专票",
        counterparty: "集成服务商",
        issueDate: "2026-03-24",
        taxRate: "6%",
        amount: "96,000.00",
        taxAmount: "5,760.00",
      },
    ],
  },
  "2026-04": {
    outputInvoices: [
      {
        id: "OUT-202604-001",
        invoiceType: "数电专票",
        counterparty: "智能工厂客户",
        issueDate: "2026-04-08",
        taxRate: "13%",
        amount: "140,000.00",
        taxAmount: "18,200.00",
      },
      {
        id: "OUT-202604-002",
        invoiceType: "数电普票",
        counterparty: "项目维保客户",
        issueDate: "2026-04-18",
        taxRate: "6%",
        amount: "80,000.00",
        taxAmount: "4,800.00",
      },
    ],
    inputInvoices: [
      {
        id: "IN-202604-021",
        invoiceType: "数电专票",
        counterparty: "系统设备商",
        issueDate: "2026-04-09",
        taxRate: "13%",
        amount: "84,000.00",
        taxAmount: "10,920.00",
      },
      {
        id: "IN-202604-022",
        invoiceType: "纸质专票",
        counterparty: "实施外包服务商",
        issueDate: "2026-04-16",
        taxRate: "6%",
        amount: "160,000.00",
        taxAmount: "9,600.00",
      },
      {
        id: "IN-202604-023",
        invoiceType: "数电专票",
        counterparty: "办公耗材商",
        issueDate: "2026-04-20",
        taxRate: "13%",
        amount: "18,000.00",
        taxAmount: "2,340.00",
      },
    ],
  },
};

export function getTaxMonthData(month: string): TaxMonthData {
  return taxDataByMonth[month] ?? { outputInvoices: [], inputInvoices: [] };
}

export function getDefaultSelectedIds(rows: TaxInvoiceRecord[]) {
  return rows.map((row) => row.id);
}

function parseMoney(value: string) {
  return Number(value.replace(/,/g, ""));
}

export function formatMoney(value: number) {
  return value.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

export function calculateTaxSummary(
  outputInvoices: TaxInvoiceRecord[],
  inputInvoices: TaxInvoiceRecord[],
): TaxSummary {
  const outputTax = outputInvoices.reduce((sum, row) => sum + parseMoney(row.taxAmount), 0);
  const inputTax = inputInvoices.reduce((sum, row) => sum + parseMoney(row.taxAmount), 0);
  const deductibleTax = Math.min(outputTax, inputTax);
  const payableTax = outputTax - deductibleTax;
  const carryForwardTax = inputTax - deductibleTax;

  return {
    outputTax: formatMoney(outputTax),
    inputTax: formatMoney(inputTax),
    deductibleTax: formatMoney(deductibleTax),
    resultLabel: payableTax >= 0.005 ? "本月应纳税额" : "本月留抵税额",
    resultAmount: formatMoney(payableTax >= 0.005 ? payableTax : carryForwardTax),
  };
}
