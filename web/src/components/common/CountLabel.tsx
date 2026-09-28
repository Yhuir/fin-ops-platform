import "./countLabel.css";

/** Display only. Undefined means unknown, never zero; callers own freshness and I/O. */
export default function CountLabel({ value, unit = "", spaced = false }: {
  value: number | null | undefined;
  unit?: string;
  spaced?: boolean;
}) {
  return <span className={`stable-count stable-count__number${unit ? " stable-count--unit" : ""}`}>{`${value ?? "—"}${spaced ? " " : ""}${unit}`}</span>;
}

/** Reserve the whole option, while the visible label and count stay tightly centred. */
export function CountedLabel({ label, value, unit = "", spaced = false }: {
  label: string; value: number | null | undefined; unit?: string; spaced?: boolean;
}) {
  return <span className="counted-label" data-sizing={`${label} 000000${spaced ? " " : ""}${unit}`}>
    <span className="counted-label__content"><span>{label}</span>{" "}<CountLabel value={value} unit={unit} spaced={spaced} /></span>
  </span>;
}
