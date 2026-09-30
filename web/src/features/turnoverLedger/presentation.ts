import { formatMoney as formatDecimal } from "../money";

export function formatMoney(value: string | number | null | undefined) {
  const [integer, fraction] = formatDecimal(value, "—").split(".");
  return fraction === undefined ? integer : `${integer.replace(/\B(?=(\d{3})+(?!\d))/g, ",")}.${fraction}`;
}

export function formatNullable(value: string | number | null | undefined) {
  return value === null || value === undefined || value === "" ? "—" : String(value);
}
