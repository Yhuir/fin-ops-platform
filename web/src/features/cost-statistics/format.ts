import { formatMoney } from "../money";

export function formatCostAmount(value: string | number | null | undefined): string {
  return formatMoney(value, "--");
}
