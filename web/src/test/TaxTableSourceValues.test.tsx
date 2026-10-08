import { render, screen, within } from "@testing-library/react";
import { vi } from "vitest";
import TaxCertificationTable from "../components/tax/TaxCertificationTable";
import TaxCertificationSummary from "../components/tax/TaxCertificationSummary";
import { taxCertificationFixture } from "./taxCertificationFixture";

test("distinguishes missing money from zero without inventing a source amount", () => {
  const result = taxCertificationFixture();
  result.rows[0].amount = null; result.rows[0].tax_amount = "0.00";
  render(<TaxCertificationTable result={result} query={{ status: "all", sort_by: "issue_date", sort_direction: "desc", page: 1, page_size: 50 }} loading={false} onPageChange={vi.fn()} onSortChange={vi.fn()} />);
  const row = screen.getByText(result.rows[0].digital_invoice_no!).closest("tr")!;
  expect(within(row).getAllByText("—").length).toBeGreaterThan(0);
  expect(within(row).getByText("0.00")).toBeInTheDocument();
  expect(within(row).queryByRole("checkbox")).not.toBeInTheDocument();
});
test("single status summary shows only its row and exposes missing totals", () => {
  const result = taxCertificationFixture(); result.summary.uncertified.missing_amount_count = 1;
  render(<TaxCertificationSummary status="uncertified" summary={result.summary} />);
  expect(screen.queryByLabelText("已认证统计")).not.toBeInTheDocument();
  expect(screen.getByLabelText("未认证统计")).toHaveTextContent("缺失 1");
});
