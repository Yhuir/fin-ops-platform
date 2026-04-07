type BankAccountValueProps = {
  value: string;
  variant?: "plain" | "tag";
};

export function splitBankAccountLabel(value: string) {
  const normalizedValue = value.trim();
  if (!normalizedValue || normalizedValue === "--" || normalizedValue === "—") {
    return null;
  }

  const compactValue = normalizedValue.replace(/\s+/g, " ").trim();
  const exactMatch = compactValue.match(/^(.*?)(?:\s+账户)?\s+(\d{4})$/);
  if (exactMatch) {
    const primary = exactMatch[1]?.replace(/\s*账户\s*$/, "").trim();
    const secondary = exactMatch[2]?.trim();
    if (primary && secondary) {
      return { primary, secondary };
    }
  }

  const tokens = compactValue.split(" ").filter(Boolean);
  const lastToken = tokens[tokens.length - 1] ?? "";
  if (/^\d{4}$/.test(lastToken) && tokens.length > 1) {
    const primary = tokens.slice(0, -1).join(" ").replace(/\s*账户\s*$/, "").trim();
    if (primary) {
      return {
        primary,
        secondary: lastToken,
      };
    }
  }

  return null;
}

export default function BankAccountValue({ value, variant = "plain" }: BankAccountValueProps) {
  const parts = splitBankAccountLabel(value);
  const className = variant === "tag" ? "bank-account-value bank-account-tag" : "bank-account-value";

  if (!parts) {
    return <span className={className}>{value}</span>;
  }

  if (variant === "tag") {
    return (
      <span className={className}>
        <span className="bank-account-primary">{parts.primary}</span>
        <span className="bank-account-secondary">{parts.secondary}</span>
      </span>
    );
  }

  return (
    <span className={className}>
      <span className="bank-account-primary">{parts.primary}</span>
      <span className="bank-account-secondary">{parts.secondary}</span>
    </span>
  );
}
