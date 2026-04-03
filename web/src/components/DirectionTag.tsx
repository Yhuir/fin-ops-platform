type DirectionTagProps = {
  direction: string;
};

export default function DirectionTag({ direction }: DirectionTagProps) {
  const normalizedDirection = direction === "收入" ? "收入" : "支出";
  return (
    <span className={`direction-tag direction-tag-${normalizedDirection === "收入" ? "inflow" : "outflow"}`}>
      {normalizedDirection}
    </span>
  );
}
