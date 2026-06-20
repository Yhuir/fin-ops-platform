import { expect, type Page } from "./strictTest";

const DEFAULT_UNEXPECTED_SUCCESS_ERROR_PATTERN =
  /操作失败|加载失败|保存失败|刷新失败|导出失败|导入失败|导入任务创建失败|后台导入失败|后台导入任务创建失败|关联失败|撤回失败|校验失败|同步.*失败|未执行|未创建|未写入|请稍后重试|网络暂时失败|read model|读模型.*失败|关系已写入，关联台刷新未完成|操作同步等待超时/i;

export async function expectNoUnexpectedSuccessUiErrors(
  page: Page,
  options: {
    allowText?: RegExp;
    errorPattern?: RegExp;
  } = {},
) {
  await expect(page.getByRole("dialog", { name: "操作失败" })).toHaveCount(0);

  const bodyText = (await page.locator("body").innerText()).replace(/\s+/g, " ").trim();
  const allowedText = options.allowText;
  const textToCheck = allowedText ? bodyText.replace(allowedText, "") : bodyText;
  const errorPattern = options.errorPattern ?? DEFAULT_UNEXPECTED_SUCCESS_ERROR_PATTERN;

  expect(errorPattern.test(textToCheck), textToCheck.slice(0, 500)).toBe(false);
}
