import { readFileSync } from "node:fs";

import { muiTheme } from "../app/muiTheme";

describe("table alignment styles", () => {
  test("centers MUI table cells through the shared theme", () => {
    const tableCellOverrides = muiTheme.components?.MuiTableCell?.styleOverrides;

    expect(tableCellOverrides?.root).toMatchObject({
      textAlign: "center",
      verticalAlign: "middle",
    });
    expect(tableCellOverrides?.head).toMatchObject({
      textAlign: "center",
      verticalAlign: "middle",
    });
    expect(tableCellOverrides?.body).toMatchObject({
      textAlign: "center",
      verticalAlign: "middle",
    });
    expect(tableCellOverrides?.alignLeft).toMatchObject({ textAlign: "center" });
    expect(tableCellOverrides?.alignRight).toMatchObject({ textAlign: "center" });
  });

  test("centers app table surfaces that do not use the MUI table theme", () => {
    const source = readFileSync("src/app/styles.css", "utf8");

    expect(source).toMatch(/\.MuiDataGrid-root \.MuiDataGrid-columnHeader,\s*\.MuiDataGrid-root \.MuiDataGrid-cell\s*\{[^}]*justify-content:\s*center\s*!important[^}]*text-align:\s*center\s*!important[^}]*align-items:\s*center/s);
    expect(source).toMatch(/\.MuiDataGrid-root \.MuiDataGrid-columnHeaderTitleContainer\s*\{[^}]*justify-content:\s*center\s*!important/s);
    expect(source).toMatch(/\.grid-table th,\s*\.grid-table td\s*\{[^}]*text-align:\s*center[^}]*vertical-align:\s*middle/s);
    expect(source).toMatch(/\.grid-table th\.cell-money,\s*\.grid-table td\.cell-money\s*\{[^}]*text-align:\s*center/s);
    expect(source).toMatch(/\.cost-table th,\s*\.cost-table td\s*\{[^}]*text-align:\s*center[^}]*vertical-align:\s*middle/s);
    expect(source).toMatch(/\.bank-transaction-table \.MuiTableCell-root\s*\{[^}]*text-align:\s*center[^}]*vertical-align:\s*middle/s);
  });
});
