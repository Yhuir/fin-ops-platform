type WorkbenchSearchBoxProps = {
  onOpen: () => void;
};

export default function WorkbenchSearchBox({ onOpen }: WorkbenchSearchBoxProps) {
  return (
    <button
      aria-label="打开关联台搜索"
      className="workbench-search-entry"
      type="button"
      onClick={onOpen}
    >
      <strong>搜索</strong>
    </button>
  );
}
