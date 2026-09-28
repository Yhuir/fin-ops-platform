import "./countLabel.css";

/** Display only. Undefined means unknown, never zero; callers own freshness and I/O. */
export default function CountLabel({ value, unit = "", spaced = false }: {
  value: number | null | undefined;
  unit?: string;
  spaced?: boolean;
}) {
  return <span className={`stable-count stable-count__number${unit ? " stable-count--unit" : ""}`}>{`${value ?? "—"}${spaced ? " " : ""}${unit}`}</span>;
}
