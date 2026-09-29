import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { apiRequestJson } from "../features/apiClient";
import BankTransactionDrawer from "../features/bankSplits/BankTransactionDrawer";

vi.mock("../features/apiClient", () => ({ apiRequestJson: vi.fn() }));
vi.mock("../features/bankSplits/BankSplitEditor", () => ({
  default: ({ transactionId }: { transactionId: string }) => <div data-testid="split-editor">{transactionId}</div>,
}));

const request = vi.mocked(apiRequestJson);
const sourceDetail = (note: string) => ({ detail_available: true, sections: [{ title: "交易信息", fields: [
  { label: "备注", value: note }, { label: "余额", value: 0 },
] }] });

beforeEach(() => request.mockReset());

test("loads exact source detail once, preserves source zero, and retains split controls", async () => {
  request.mockResolvedValue(sourceDetail("银行原始备注"));
  render(<BankTransactionDrawer transactionId="bank / 1" onClose={() => undefined} />);
  expect(await screen.findByText("银行原始备注")).toBeInTheDocument();
  expect(screen.getByText("0")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", {name: "流水子项拆分"}));
  expect(screen.getByTestId("split-editor")).toHaveTextContent("bank / 1");
  expect(request).toHaveBeenCalledTimes(1);
  expect(request).toHaveBeenCalledWith("/api/bank-transactions/bank%20%2F%201/source-detail", expect.objectContaining({ method: "GET" }), { allowHtmlFallback: false });
});

test("switching objects never displays late source facts from the previous bank", async () => {
  let finishFirst!: (value: unknown) => void;
  request.mockImplementationOnce(() => new Promise(resolve => { finishFirst = resolve; }));
  request.mockResolvedValueOnce(sourceDetail("第二笔来源"));
  const { rerender } = render(<BankTransactionDrawer transactionId="first" onClose={() => undefined} />);
  rerender(<BankTransactionDrawer transactionId="second" onClose={() => undefined} />);
  expect(await screen.findByText("第二笔来源")).toBeInTheDocument();
  await act(async () => finishFirst(sourceDetail("过期第一笔")));
  expect(screen.queryByText("过期第一笔")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", {name: "流水子项拆分"}));
  expect(screen.getByTestId("split-editor")).toHaveTextContent("second");
});

test("shows a source read failure without data or split mutations", async () => {
  request.mockRejectedValue(new Error("来源读取失败"));
  render(<BankTransactionDrawer transactionId="bank-1" onClose={() => undefined} />);
  expect(await screen.findByText("来源读取失败")).toBeInTheDocument();
  expect(screen.queryByTestId("split-editor")).not.toBeInTheDocument();
});

test("an empty source field set does not remove the separately owned split editor", async () => {
  request.mockResolvedValue({ detail_available: true, sections: [] });
  render(<BankTransactionDrawer transactionId="bank-1" onClose={() => undefined} />);
  await waitFor(() => expect(screen.getByRole("button", {name: "流水子项拆分"})).toBeInTheDocument());
  fireEvent.click(screen.getByRole("button", {name: "流水子项拆分"}));
  expect(screen.getByTestId("split-editor")).toHaveTextContent("bank-1");
  expect(screen.queryByText("状态")).not.toBeInTheDocument();
});
