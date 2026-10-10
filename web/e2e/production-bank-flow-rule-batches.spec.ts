import { expect, test } from "./fixtures/strictTest";
import { expectNoUnexpectedSuccessUiErrors } from "./fixtures/successAssertions";

const enabled = process.env.FIN_OPS_E2E_PRODUCTION_SMOKE === "1";
const adminToken = process.env.FIN_OPS_E2E_ADMIN_TOKEN ?? "";

// Production verification is read-only. Do not record authentication headers.
test.use({ screenshot: "off", trace: "off", video: "off" });

test.describe("production bank flow rule batch UI", () => {
  test.skip(!enabled, "Set FIN_OPS_E2E_PRODUCTION_SMOKE=1 for the read-only production check.");
  test.skip(!adminToken, "The production token wrapper must provide FIN_OPS_E2E_ADMIN_TOKEN.");

  test("filters the full result and independently expands batches with shared source details", async ({ page, baseURL }, info) => {
    test.setTimeout(120_000);
    const writes: string[] = [];
    await page.route("**/*", async route => {
      if (!["GET", "HEAD", "OPTIONS"].includes(route.request().method())) {
        writes.push(`${route.request().method()} ${new URL(route.request().url()).pathname}`);
        await route.abort("blockedbyclient");
      } else await route.continue();
    });
    await page.context().addCookies([{ name: "Admin-Token", value: adminToken,
      domain: new URL(baseURL!).hostname, path: "/", secure: true, sameSite: "Lax" }]);
    await page.addInitScript(() => {
      const observed = window as typeof window & { categoryFeedbackMs: number[] };
      observed.categoryFeedbackMs = [];
      document.addEventListener("click", event => {
        const button = event.target instanceof Element ? event.target.closest(".bank-flow-rule-batches-rail__item") : null;
        if (!button || button.getAttribute("aria-pressed") === "true") return;
        const start = performance.now();
        const observer = new MutationObserver(() => {
          if (button.getAttribute("aria-pressed") !== "true") return;
          observer.disconnect();
          requestAnimationFrame(() => requestAnimationFrame(() => observed.categoryFeedbackMs.push(performance.now() - start)));
        });
        observer.observe(button, { attributes: true, attributeFilter: ["aria-pressed"] });
      }, true);
    });

    const listPath = "/fin-ops-api/api/bank-flow-rule-batches";
    const allResponse = await page.request.get(`${listPath}?bucket=submitted&page=1&page_size=200`);
    expect(allResponse.status()).toBe(200);
    const all = await allResponse.json();
    expect(all.pagination.total).toBeGreaterThanOrEqual(2);
    const batches = [...all.batches];
    for (let current = 2; current <= Math.ceil(all.pagination.total / 200); current++) {
      const response = await page.request.get(`${listPath}?bucket=submitted&page=${current}&page_size=200`);
      expect(response.status()).toBe(200);
      const payload = await response.json();
      expect(payload.summary).toEqual(all.summary);
      batches.push(...payload.batches);
    }
    expect(batches).toHaveLength(all.pagination.total);
    const codes = [...new Set<string>(batches.map(batch => batch.batch_type))].slice(0, 2);
    expect(codes).toHaveLength(2);
    const query = new URLSearchParams({ bucket: "submitted", page: "1", page_size: "1" });
    codes.forEach(code => query.append("type", code));
    const filteredResponse = await page.request.get(`${listPath}?${query}`);
    expect(filteredResponse.status()).toBe(200);
    const filtered = await filteredResponse.json();
    const expected = batches.filter(batch => codes.includes(batch.batch_type));
    expect(filtered.pagination.total).toBe(expected.length);
    expect(filtered.batches.map((batch: { batch_id: string }) => batch.batch_id)).toEqual([expected[0].batch_id]);
    expect(filtered.summary).toEqual(all.summary);
    const invalid = await page.request.get(`${listPath}?type=all&type=${encodeURIComponent(codes[0])}&page=1&page_size=50`);
    expect(invalid.status()).toBe(400);
    expect((await invalid.json()).error).toBe("invalid_bank_flow_rule_batch_type");

    await page.setViewportSize({ width: 1440, height: 980 });
    await page.goto("/fin-ops/bank-flow-rule-batches", { waitUntil: "domcontentloaded" });
    await expect(page.getByRole("heading", { name: "流水规则批量处理", exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "查看全部分类" })).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByRole("grid")).toHaveCount(0);
    await page.getByRole("radio", { name: /^已提交/ }).click();
    const navigation = page.getByRole("navigation", { name: "流水分类" });
    const groups = new Map<string, typeof all.summary.categories>();
    for (const category of all.summary.categories) {
      if (category.submitted <= 0) continue;
      expect(typeof category.primary_label).toBe("string");
      const group = groups.get(category.primary_label) ?? [];
      group.push(category);
      groups.set(category.primary_label, group);
    }
    expect(groups.size).toBeGreaterThanOrEqual(2);
    for (const [primary, categories] of groups) {
      const childCount = new Set(categories.map((category: { sub_label: string }) => category.sub_label).filter(Boolean)).size;
      await expect(navigation.getByRole("button", { name: `${primary} ${childCount} 个子标签`, exact: true })).toBeVisible();
    }
    const primaryNames = [...groups.keys()].slice(0, 2);
    const waitForList = () => page.waitForResponse(response => response.request().method() === "GET"
      && new URL(response.url()).pathname === listPath);
    for (let sample = 0; sample < 30; sample++) {
      const primary = primaryNames[sample % 2];
      const categories = groups.get(primary)!;
      const childCount = new Set(categories.map((category: { sub_label: string }) => category.sub_label).filter(Boolean)).size;
      const responsePromise = waitForList();
      const button = navigation.getByRole("button", { name: `${primary} ${childCount} 个子标签`, exact: true });
      await button.click();
      const response = await responsePromise;
      expect(response.status()).toBe(200);
      expect(new URL(response.url()).searchParams.getAll("type")).toEqual(categories.map((category: { code: string }) => category.code));
      await expect(button).toHaveAttribute("aria-pressed", "true");
      await expect(page.getByText("流水加载中", { exact: true })).toHaveCount(0);
    }
    const selectedPrimary = primaryNames[1];
    const selectedCategories = groups.get(selectedPrimary)!;
    const child = selectedCategories[0].sub_label;
    const childLabel = child || "主标签本身";
    const childRows = all.summary.label_counts.find((item: { primary_label: string; sub_label: string | null }) =>
      item.primary_label === selectedPrimary && item.sub_label === child).submitted_row_count;
    const childResponsePromise = waitForList();
    const childButton = navigation.getByRole("button", { name: `${selectedPrimary} / ${childLabel} ${childRows} 笔`, exact: true });
    await childButton.click();
    const childResponse = await childResponsePromise;
    expect(childResponse.status()).toBe(200);
    expect(new URL(childResponse.url()).searchParams.getAll("type")).toEqual(selectedCategories
      .filter((category: { sub_label: string }) => category.sub_label === child).map((category: { code: string }) => category.code));
    await expect(childButton).toHaveAttribute("aria-pressed", "true");
    const feedbackMs = await page.evaluate(() => (window as typeof window & { categoryFeedbackMs: number[] }).categoryFeedbackMs);
    expect(feedbackMs.length).toBeGreaterThanOrEqual(30);
    const sorted = [...feedbackMs].sort((a, b) => a - b);
    await info.attach("category-feedback.json", { body: JSON.stringify({ samples: feedbackMs, sampleCount: feedbackMs.length,
      p50: sorted[Math.ceil(sorted.length * .5) - 1], p95: sorted[Math.ceil(sorted.length * .95) - 1],
      p99: sorted[Math.ceil(sorted.length * .99) - 1], clock: "browser click to selected state plus two animation frames" }), contentType: "application/json" });
    const overviewResponse = waitForList();
    await page.getByRole("button", { name: "查看全部分类" }).click();
    expect((await overviewResponse).status()).toBe(200);
    await expect(page.getByRole("button", { name: "查看全部分类" })).toHaveAttribute("aria-pressed", "true");
    const sections = page.locator(".bank-flow-rule-batches-batch");
    await expect(sections.first()).toBeVisible();
    for (const index of [0, 1]) {
      await sections.nth(index).getByRole("button", { name: /^展开批次/ }).click();
      await expect(sections.nth(index).getByRole("grid")).toBeVisible();
    }
    await expect(page.getByRole("grid")).toHaveCount(2);
    await expect.poll(() => page.locator(".bank-flow-rule-batches-expansion[data-expanded='true']").evaluateAll(nodes =>
      nodes.every(node => !node.getAnimations().some(animation => animation.playState === "running")
        && node.getBoundingClientRect().height > 0))).toBe(true);
    await expect(page.getByRole("button", { name: "查看流水", exact: true })).toHaveCount(0);
    await page.screenshot({ path: info.outputPath("production-multiple-expanded-1440.png"), fullPage: true });
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.screenshot({ path: info.outputPath("production-multiple-expanded-1280.png"), fullPage: true });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);

    const detailResponsePromise = page.waitForResponse(response => response.request().method() === "GET"
      && new URL(response.url()).pathname.endsWith("/source-detail"));
    await sections.first().getByRole("button", { name: /^查看银行流水 .* 详情$/ }).first().click();
    const drawer = page.getByRole("dialog", { name: "银行流水详情", exact: true });
    await expect(drawer).toBeVisible();
    const detailResponse = await detailResponsePromise;
    expect(detailResponse.status()).toBe(200);
    const detail = await detailResponse.json();
    expect(detail.detail_available).toBe(true);
    expect(detail.sections.length).toBeGreaterThan(0);
    await expect(drawer.getByText("对方户名", { exact: true }).first()).toBeVisible();
    await drawer.getByRole("button", { name: "关闭详情抽屉", exact: true }).click();
    await expect(drawer).toHaveCount(0);
    await expect(page.getByRole("grid")).toHaveCount(2);
    await page.getByRole("button", { name: "收起全部", exact: true }).click();
    await expect(page.getByRole("grid")).toHaveCount(0);
    expect(writes).toEqual([]);
    await expectNoUnexpectedSuccessUiErrors(page);
    await info.attach("production-batch-read-contract", { body: JSON.stringify({
      totalBatches: all.pagination.total, filteredTotal: filtered.pagination.total,
      checkedCodes: codes.length, simultaneousExpanded: 2, mutatingRequests: writes.length,
    }), contentType: "application/json" });
  });
});
