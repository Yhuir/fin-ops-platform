import { describe, expect, test, vi } from "vitest";

import { buildEtcOaDraftReviewUrl, tryOpenEtcOaDraftEditDialog } from "../features/etc/oaNavigation";

describe("ETC OA navigation", () => {
  test("adds an OA list filter for the created ETC batch", () => {
    const url = buildEtcOaDraftReviewUrl(
      "https://www.yn-sourcing.com/oa/#/normal/forms/form/2?formId=2&id=oa-draft-001",
      "etc_20260503_001",
    );

    const hashQuery = url.split("?")[1] ?? "";
    const params = new URLSearchParams(hashQuery);
    const conditions = JSON.parse(params.get("conditions") ?? "[]") as Array<Record<string, string>>;

    expect(url).toContain("/oa/#/normal/forms/form/2");
    expect(params.get("formId")).toBe("2");
    expect(params.get("id")).toBe("oa-draft-001");
    expect(params.get("finOpsEtcAutoEdit")).toBe("1");
    expect(conditions).toEqual([
      {
        field: "cause",
        condition: "regex",
        value: "etc_20260503_001",
      },
    ]);
  });

  test("opens the edit dialog for the OA row that contains the created ETC batch", () => {
    document.body.innerHTML = `
      <table>
        <tbody>
          <tr class="el-table__row">
            <td>其他申请</td>
            <td><button>修改</button></td>
          </tr>
          <tr class="el-table__row">
            <td>ETC批量提交 etc_batch_id=etc_20260503_001</td>
            <td><button>详情</button><button id="target">修改</button></td>
          </tr>
        </tbody>
      </table>
    `;
    const clickSpy = vi.spyOn(document.getElementById("target") as HTMLButtonElement, "click");

    const didOpen = tryOpenEtcOaDraftEditDialog(
      { closed: false, document } as unknown as Window,
      "etc_20260503_001",
    );

    expect(didOpen).toBe(true);
    expect(clickSpy).toHaveBeenCalledTimes(1);
  });
});
