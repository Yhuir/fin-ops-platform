type WorkbenchSearchBoxProps = {
  onOpen: () => void;
};

export default function WorkbenchSearchBox({ onOpen }: WorkbenchSearchBoxProps) {
  return (
    <button
      aria-label="搜索"
      className="workbench-search-entry"
      type="button"
      onClick={onOpen}
    >
      <span className="workbench-search-entry-placeholder">搜索</span>
    </button>
  );
}
