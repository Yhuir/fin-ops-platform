import { Button, SearchField, Spinner } from "@heroui/react";
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
  maxLength?: number;
  onCompositionChange?: (composing: boolean) => void;
  pending?: boolean;
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
  maxLength,
  onCompositionChange,
  pending = false,
}: QuerySearchProps) {
  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    onSubmit();
  };

  return (
    <form className={`query-search${className ? ` ${className}` : ""}`} onSubmit={handleSubmit} role="search">
      <SearchField aria-label={ariaLabel} fullWidth isDisabled={disabled} onChange={onChange} value={value}>
        <SearchField.Group className="query-search__field">
          {pending ? <Spinner aria-label="搜索中" color="current" size="sm" /> : <SearchField.SearchIcon />}
          <SearchField.Input
            maxLength={maxLength}
            onCompositionEnd={() => onCompositionChange?.(false)}
            onCompositionStart={() => onCompositionChange?.(true)}
            placeholder={placeholder}
          />
          {value ? <SearchField.ClearButton aria-label="清除查询" onPress={onClear} /> : null}
        </SearchField.Group>
      </SearchField>
      <Button isDisabled={disabled} size="sm" type="submit" variant="secondary">
        查询
      </Button>
    </form>
  );
}
