import { formatMoney } from "../money";

export function formatCostAmount(value: string | number | null | undefined): string {
  return formatMoney(value, "--");
}

export function formatProjectCostAmount(value: string | number | null | undefined): string {
  return formatCostAmount(value).replace(/^(-?)(\d+)(\.\d{2})$/, (_, sign: string, integer: string, fraction: string) =>
    `${sign}${integer.replace(/\B(?=(\d{3})+(?!\d))/g, ",")}${fraction}`,
  );
}
