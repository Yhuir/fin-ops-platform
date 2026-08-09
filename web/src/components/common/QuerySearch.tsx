import { Button, SearchField } from "@heroui/react";
import type { FormEvent } from "react";

type QuerySearchProps = {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  onClear: () => void;
  ariaLabel: string;
  placeholder: string;
  className?: string;
  disabled?: boolean;
};

export default function QuerySearch({
  value,
  onChange,
  onSubmit,
  onClear,
  ariaLabel,
  placeholder,
  className,
  disabled = false,
}: QuerySearchProps) {
  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    onSubmit();
  };

  return (
    <form className={`query-search${className ? ` ${className}` : ""}`} onSubmit={handleSubmit} role="search">
      <SearchField aria-label={ariaLabel} fullWidth isDisabled={disabled} onChange={onChange} value={value}>
        <SearchField.Group className="query-search__field">
          <SearchField.SearchIcon />
          <SearchField.Input placeholder={placeholder} />
          {value ? <SearchField.ClearButton aria-label="清除查询" onPress={onClear} /> : null}
        </SearchField.Group>
      </SearchField>
      <Button isDisabled={disabled} size="sm" type="submit" variant="secondary">
        查询
      </Button>
    </form>
  );
}
