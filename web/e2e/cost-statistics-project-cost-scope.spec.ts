import { expect, test } from "./fixtures/strictTest";
import { expectNoUnexpectedSuccessUiErrors } from "./fixtures/successAssertions";
import { installDeterministicApiMocks } from "./fixtures/apiMocks";

test("scope drawer saves once, refreshes costs, and stays readable at narrow widths", async ({ page }, testInfo) => {
  await installDeterministicApiMocks(page, { sessionMode: "user" });
  let version = 1, codes = ["material"], writes = 0, reads = 0;
  const available_tags = [
    { code: "internal_transfer", label: "内部往来款", path: ["内部往来款"], status: "active", direction: "any", can_select: true },
    { code: "material", label: "材料款", path: ["采购", "材料款"], status: "active", direction: "expense", can_select: true },
    { code: "refund", label: "付错退款", path: ["付错退款"], status: "active", direction: "income", can_select: false },
    ...Array.from({ length: 36 }, (_, index) => ({ code: `tag-${index}`, label: `归档费用${index}`, path: ["项目开销", `较长的设备采购与安装调试费用标签 ${index}`], status: "archived", direction: "expense", can_select: true })),
  ];
  await page.route("**/api/cost-statistics/project-cost-scope", async route => {
    if (route.request().method() === "PUT") {
      const body = route.request().postDataJSON();
      expect(body.expected_version).toBe(version); codes = body.selected_tag_codes; version++; writes++;
    } else reads++;
    await route.fulfill({ json: { version, selected_tag_codes: codes, available_tags, can_save: true, changed: true } });
  });
  await page.goto("/cost-statistics");
  await expect(page.getByRole("button", { name: "项目成本范围", exact: true })).toBeEnabled();
  expect(reads).toBe(0);
  await page.getByRole("button", { name: "项目成本范围", exact: true }).click();
  const drawer = page.getByRole("dialog", { name: "项目成本范围" });
  await expect(drawer.getByRole("checkbox")).toHaveCount(39);
  await expect(drawer.getByRole("checkbox", { name: /付错退款/ })).toBeDisabled();
  await page.screenshot({ animations: "disabled", path: testInfo.outputPath("scope-wide.png") });
  await drawer.getByText("内部往来款", { exact: true }).click();
  expect(writes).toBe(0);
  const fresh = page.waitForResponse(response => response.url().includes("/cost-statistics/explorer") && response.request().method() === "GET");
  await drawer.getByRole("button", { name: "保存范围" }).click();
  await fresh; await expect(drawer).not.toBeVisible();
  expect(writes).toBe(1); expect(codes).toContain("internal_transfer");
  await page.getByRole("button", { name: "项目成本范围", exact: true }).click();
  await expect(drawer.getByRole("checkbox", { name: "内部往来款", exact: true })).toBeChecked();
  await page.setViewportSize({ width: 600, height: 800 });
  await page.screenshot({ animations: "disabled", path: testInfo.outputPath("scope-narrow.png") });
  await expectNoUnexpectedSuccessUiErrors(page);
  const box = await drawer.boundingBox(); expect(box!.width).toBeLessThanOrEqual(600);
  await expect(drawer.getByRole("button", { name: "保存范围" })).toBeInViewport();
});
