import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import SupportingDocumentGalleryDrawer from "../components/imports/SupportingDocumentGalleryDrawer";
import { listWorkbenchOaSupportingDocumentGallery } from "../features/workbench/api";
import type { WorkbenchOaSupportingDocument } from "../features/workbench/types";

vi.mock("../features/workbench/api", async () => {
  const actual = await vi.importActual<typeof import("../features/workbench/api")>("../features/workbench/api");
  return {
    ...actual,
    listWorkbenchOaSupportingDocumentGallery: vi.fn(),
  };
});

const document = (
  id: string,
  fileName: string,
  contentType: string,
  createdAt: string,
): WorkbenchOaSupportingDocument => ({
  id,
  relationCaseId: "CASE-1",
  oaRowId: "oa-1",
  expenseItemId: "oa-1:item:0",
  fileName,
  contentType,
  sha256: `sha-${id}`,
  sizeBytes: 2048,
  createdBy: "finance-user",
  createdAt,
  contentUrl: `/api/documents/${id}/content`,
  thumbnailUrl: `/api/documents/${id}/thumbnail`,
});

afterEach(() => vi.clearAllMocks());

describe("SupportingDocumentGalleryDrawer", () => {
  test("loads only after opening, pages by nine, and previews in the same drawer", async () => {
    const user = userEvent.setup();
    const firstDocuments = Array.from({ length: 9 }, (_, index) => document(
      `document-${index + 1}`,
      index === 0 ? "voucher.pdf" : `voucher-${index + 1}.png`,
      index === 0 ? "application/pdf" : "image/png",
      `2026-08-${23 - Math.floor(index / 3)}T08:00:00+08:00`,
    ));
    vi.mocked(listWorkbenchOaSupportingDocumentGallery)
      .mockResolvedValueOnce({ documents: firstDocuments, pageSize: 9, hasMore: true, nextCursor: "cursor-2" })
      .mockResolvedValueOnce({
        documents: [document("document-10", "voucher-10.png", "image/png", "2026-08-20T08:00:00+08:00")],
        pageSize: 9,
        hasMore: false,
        nextCursor: null,
      });

    const { rerender } = render(<SupportingDocumentGalleryDrawer onClose={vi.fn()} open={false} />);
    expect(listWorkbenchOaSupportingDocumentGallery).not.toHaveBeenCalled();

    rerender(<SupportingDocumentGalleryDrawer onClose={vi.fn()} open />);
    expect(await screen.findByText("voucher.pdf")).toBeInTheDocument();
    expect(listWorkbenchOaSupportingDocumentGallery).toHaveBeenCalledWith(expect.objectContaining({ cursor: "" }));
    expect(screen.getAllByRole("button").filter((button) => button.textContent?.includes("来源："))).toHaveLength(9);

    await user.click(screen.getByRole("button", { name: /voucher\.pdf/ }));
    expect(screen.getByRole("dialog", { name: "查看补充凭证" })).toBeInTheDocument();
    expect(screen.getByLabelText("voucher.pdf PDF 预览")).toHaveAttribute("data", "/api/documents/document-1/content");

    await user.click(screen.getByRole("button", { name: "返回全部凭证" }));
    await user.click(screen.getByRole("button", { name: "加载更多" }));
    expect(await screen.findByText("voucher-10.png")).toBeInTheDocument();
    expect(listWorkbenchOaSupportingDocumentGallery).toHaveBeenLastCalledWith(expect.objectContaining({ cursor: "cursor-2" }));
    expect(screen.queryByRole("button", { name: "加载更多" })).not.toBeInTheDocument();
  });

  test("shows an empty state and supports closing without loading again", async () => {
    const onClose = vi.fn();
    vi.mocked(listWorkbenchOaSupportingDocumentGallery).mockResolvedValue({
      documents: [],
      pageSize: 9,
      hasMore: false,
      nextCursor: null,
    });

    render(<SupportingDocumentGalleryDrawer onClose={onClose} open />);

    expect(await screen.findByText("暂无补充凭证")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "关闭补充凭证" }));
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
    expect(listWorkbenchOaSupportingDocumentGallery).toHaveBeenCalledTimes(1);
  });
});
