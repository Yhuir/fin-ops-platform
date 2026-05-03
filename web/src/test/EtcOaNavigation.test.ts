import { describe, expect, test } from "vitest";

import { buildEtcOaDraftReviewUrl } from "../features/etc/oaNavigation";

describe("ETC OA navigation", () => {
  test("opens the stable OA payment request list without draft filters or auto edit flags", () => {
    const url = buildEtcOaDraftReviewUrl(
      "https://www.yn-sourcing.com/oa/#/normal/forms/form/2?formId=2&id=oa-draft-001&conditions=%5B%5D&finOpsEtcAutoEdit=1",
    );

    const hashQuery = url.split("#/normal/forms/form/2?")[1] ?? "";
    const params = new URLSearchParams(hashQuery);

    expect(url).toContain("/oa/#/normal/forms/form/2");
    expect(params.get("formId")).toBe("2");
    expect(params.get("id")).toBeNull();
    expect(params.get("conditions")).toBeNull();
    expect(params.get("finOpsEtcAutoEdit")).toBeNull();
  });
});
