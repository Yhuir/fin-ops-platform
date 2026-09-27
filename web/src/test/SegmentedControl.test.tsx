import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import SegmentedControl, { Segment, SegmentGroup } from "../components/common/SegmentedControl";

const options = [{ key: "pending", label: "待处理 3" }, { key: "saved", label: "暂存 2" }, { key: "sent", label: "已提交 1", disabled: true }];

describe("native segmented controls", () => {
  it("emits one selection, ignores reselection and disabled choices, and supports keyboard navigation", async () => {
    const user = userEvent.setup();
    const change = vi.fn();
    function Owner() {
      const [value, setValue] = useState("pending");
      return <SegmentedControl label="处理状态" value={value} options={options} onChange={next => { change(next); setValue(next); }} />;
    }
    render(<Owner />);
    await user.click(screen.getByRole("radio", { name: "待处理 3" }));
    expect(change).not.toHaveBeenCalled();
    await user.keyboard("{ArrowRight}");
    expect(screen.getByRole("radio", { name: "暂存 2" })).toHaveFocus();
    await user.keyboard(" ");
    expect(screen.getByRole("radio", { name: "暂存 2" })).toHaveAttribute("aria-checked", "true");
    expect(change).toHaveBeenCalledTimes(1);
    expect(change).toHaveBeenCalledWith("saved");
    await user.click(screen.getByRole("radio", { name: "已提交 1" }));
    expect(change).toHaveBeenCalledTimes(1);
  });

  it("keeps an empty controlled group empty and preserves one selection across visual groups", async () => {
    const user = userEvent.setup();
    function Owner() {
      const [value, setValue] = useState("project");
      return <>{[["project", "项目"], ["time", "时间"]].map(([key, label]) => <SegmentGroup key={key} aria-label={label} selectionMode="single" selectedKeys={new Set(value === key ? [key] : [])} onSelectionChange={keys => { if (keys.has(key)) setValue(key); }}>
        <Segment id={key}>{label}</Segment>
      </SegmentGroup>)}</>;
    }
    render(<Owner />);
    expect(screen.getAllByRole("radio", { checked: true })).toHaveLength(1);
    expect(screen.getByRole("radio", { name: "时间" })).toHaveAttribute("aria-checked", "false");
    await user.click(screen.getByRole("radio", { name: "时间" }));
    expect(screen.getAllByRole("radio", { checked: true })).toHaveLength(1);
    expect(screen.getByRole("radio", { name: "时间" })).toHaveAttribute("aria-checked", "true");
  });

  it("does not call the owner while busy, and preserves its selection after re-enabling", async () => {
    const user = userEvent.setup(); const change = vi.fn();
    const { rerender } = render(<SegmentedControl label="状态" value="pending" options={options} disabled onChange={change} />);
    await user.click(screen.getByRole("radio", { name: "暂存 2" }));
    expect(change).not.toHaveBeenCalled();
    rerender(<SegmentedControl label="状态" value="pending" options={options} onChange={change} />);
    expect(screen.getByRole("radio", { name: "待处理 3" })).toHaveAttribute("aria-checked", "true");
    await user.click(screen.getByRole("radio", { name: "暂存 2" }));
    expect(change).toHaveBeenCalledTimes(1);
    expect(change).toHaveBeenCalledWith("saved");
  });
});
