// Normalize persisted filter values using the same output-invoice API vocabulary.
export function normalizeOutputTaxRate(value: string): string {
  const text = value.trim();
  if (!text) return "—";
  if (text === "mixed") return "多税率";
  if (!/^[0-9]+(?:\.[0-9]+)?%?$/.test(text)) return text;
  const number = Number(text.replace(/%$/, ""));
  const percent = !text.endsWith("%") && number <= 1 ? number * 100 : number;
  return `${Number(percent.toFixed(10))}%`;
}
