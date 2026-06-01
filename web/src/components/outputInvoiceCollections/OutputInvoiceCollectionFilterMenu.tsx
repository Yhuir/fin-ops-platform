import ArrowDownwardOutlinedIcon from "@mui/icons-material/ArrowDownwardOutlined";
import ArrowUpwardOutlinedIcon from "@mui/icons-material/ArrowUpwardOutlined";
import FilterListOutlinedIcon from "@mui/icons-material/FilterListOutlined";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import Divider from "@mui/material/Divider";
import ListItemIcon from "@mui/material/ListItemIcon";
import ListItemText from "@mui/material/ListItemText";
import Menu from "@mui/material/Menu";
import MenuItem from "@mui/material/MenuItem";
import Radio from "@mui/material/Radio";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { useEffect, useMemo, useState } from "react";

export type OutputInvoiceCollectionFilterMode = "text" | "enum_single" | "enum_multi" | "date" | "money";

export type OutputInvoiceCollectionFieldConfig = {
  field: string;
  label: string;
  mode: OutputInvoiceCollectionFilterMode;
  sortable?: boolean;
  operators?: string[];
};

export type OutputInvoiceCollectionFilterOption = {
  value: string;
  label: string;
  count?: number;
};

export type OutputInvoiceCollectionFilterValue =
  | { field: string; operator: "in"; values: string[] }
  | { field: string; operator: "equals"; value: string }
  | { field: string; operator: "contains"; value: string }
  | { field: string; operator: "between"; value: { min?: string; max?: string } | [string, string] | null }
  | { field: string; operator: string; value?: string; values?: string[] };

type OutputInvoiceCollectionFilterMenuProps = {
  fieldConfig: OutputInvoiceCollectionFieldConfig;
  currentFilter?: OutputInvoiceCollectionFilterValue | null;
  options: OutputInvoiceCollectionFilterOption[];
  onApply: (filter: OutputInvoiceCollectionFilterValue) => void;
  onClear: (field: string) => void;
  onSort: (direction: "asc" | "desc") => void;
};

export default function OutputInvoiceCollectionFilterMenu({
  fieldConfig,
  currentFilter,
  options,
  onApply,
  onClear,
  onSort,
}: OutputInvoiceCollectionFilterMenuProps) {
  const [anchorEl, setAnchorEl] = useState<HTMLElement | null>(null);
  const open = Boolean(anchorEl);
  const selectedValues = useMemo(() => resolveSelectedValues(currentFilter), [currentFilter]);
  const selectedSet = useMemo(() => new Set(selectedValues), [selectedValues]);
  const [operator, setOperator] = useState<"contains" | "equals" | "between">("contains");
  const [singleValue, setSingleValue] = useState("");
  const [minValue, setMinValue] = useState("");
  const [maxValue, setMaxValue] = useState("");
  const hasActiveFilter = Boolean(currentFilter);

  useEffect(() => {
    if (!open) {
      return;
    }
    const currentOperator = currentFilter?.operator;
    if (currentOperator === "equals" || currentOperator === "contains" || currentOperator === "between") {
      setOperator(currentOperator);
    } else if (fieldConfig.mode === "text") {
      setOperator(fieldConfig.operators?.includes("contains") === false ? "equals" : "contains");
    } else {
      setOperator("between");
    }
    if (currentFilter && "value" in currentFilter) {
      const value = currentFilter.value;
      if (typeof value === "string") {
        setSingleValue(value);
        setMinValue("");
        setMaxValue("");
      } else if (Array.isArray(value)) {
        setSingleValue("");
        setMinValue(String(value[0] ?? ""));
        setMaxValue(String(value[1] ?? ""));
      } else if (value && typeof value === "object") {
        setSingleValue("");
        setMinValue(String(value.min ?? ""));
        setMaxValue(String(value.max ?? ""));
      } else {
        setSingleValue("");
        setMinValue("");
        setMaxValue("");
      }
      return;
    }
    setSingleValue("");
    setMinValue("");
    setMaxValue("");
  }, [currentFilter, fieldConfig, open]);

  const optionLabel = (option: OutputInvoiceCollectionFilterOption) => (
    option.count === undefined ? option.label : `${option.label} ${option.count}`
  );

  const applyMulti = (values: string[]) => {
    onApply({ field: fieldConfig.field, operator: "in", values });
  };

  const toggleMulti = (value: string) => {
    if (selectedSet.has(value)) {
      applyMulti(selectedValues.filter((candidate) => candidate !== value));
      return;
    }
    applyMulti([...selectedValues, value]);
  };

  const applySingle = (value: string) => {
    onApply({ field: fieldConfig.field, operator: "equals", value });
  };

  const applyValueFilter = () => {
    if (operator === "between") {
      const value = { min: minValue.trim(), max: maxValue.trim() };
      if (!value.min && !value.max) {
        onClear(fieldConfig.field);
      } else {
        onApply({ field: fieldConfig.field, operator: "between", value });
      }
    } else {
      const value = singleValue.trim();
      if (!value) {
        onClear(fieldConfig.field);
      } else {
        onApply({ field: fieldConfig.field, operator, value });
      }
    }
    setAnchorEl(null);
  };

  return (
    <>
      <Button
        aria-label={`筛选 ${fieldConfig.label}`}
        color={hasActiveFilter || selectedValues.length > 0 ? "primary" : "inherit"}
        size="small"
        startIcon={<FilterListOutlinedIcon fontSize="small" />}
        onClick={(event) => setAnchorEl(event.currentTarget)}
        sx={{
          justifyContent: "flex-start",
          maxWidth: "100%",
          minWidth: 0,
          px: 0.5,
          ".MuiButton-startIcon": { mr: 0.25 },
        }}
      >
        <Typography component="span" variant="inherit" noWrap>
          {fieldConfig.label}
        </Typography>
      </Button>
      <Menu
        anchorEl={anchorEl}
        aria-label={`${fieldConfig.label}筛选与排序`}
        MenuListProps={{ "aria-label": `${fieldConfig.label}筛选与排序` }}
        open={open}
        onClose={() => setAnchorEl(null)}
      >
        <Stack sx={{ px: 2, py: 1 }}>
          <Typography variant="subtitle2" fontWeight={900}>
            {fieldConfig.label}
          </Typography>
          <Typography variant="caption" color="text.secondary">
            筛选项来自当前后端查询上下文
          </Typography>
        </Stack>
        <MenuItem onClick={() => onSort("asc")}>
          <ListItemIcon><ArrowUpwardOutlinedIcon fontSize="small" /></ListItemIcon>
          <ListItemText>升序排序</ListItemText>
        </MenuItem>
        <MenuItem onClick={() => onSort("desc")}>
          <ListItemIcon><ArrowDownwardOutlinedIcon fontSize="small" /></ListItemIcon>
          <ListItemText>降序排序</ListItemText>
        </MenuItem>
        <Divider />
        {fieldConfig.mode === "enum_multi" ? (
          <>
            <MenuItem onClick={() => applyMulti(options.map((option) => option.value))}>全选</MenuItem>
            <MenuItem onClick={() => onClear(fieldConfig.field)}>清空</MenuItem>
            <Divider />
            {options.length === 0 ? <MenuItem disabled>暂无可选项</MenuItem> : null}
            {options.map((option) => (
              <MenuItem
                key={option.value}
                aria-checked={selectedSet.has(option.value)}
                role="menuitemcheckbox"
                onClick={() => toggleMulti(option.value)}
              >
                <Checkbox checked={selectedSet.has(option.value)} size="small" tabIndex={-1} />
                <ListItemText>{optionLabel(option)}</ListItemText>
              </MenuItem>
            ))}
          </>
        ) : null}
        {fieldConfig.mode === "enum_single" ? (
          <>
            <MenuItem onClick={() => onClear(fieldConfig.field)}>清空</MenuItem>
            <Divider />
            {options.length === 0 ? <MenuItem disabled>暂无可选项</MenuItem> : null}
            {options.map((option) => (
              <MenuItem
                key={option.value}
                aria-checked={selectedSet.has(option.value)}
                role="menuitemradio"
                onClick={() => applySingle(option.value)}
              >
                <Radio checked={selectedSet.has(option.value)} size="small" tabIndex={-1} />
                <ListItemText>{optionLabel(option)}</ListItemText>
              </MenuItem>
            ))}
          </>
        ) : null}
        {fieldConfig.mode !== "enum_multi" && fieldConfig.mode !== "enum_single" ? (
          <Stack spacing={1.25} sx={{ px: 2, py: 1.5, width: 300 }}>
            <Button
              size="small"
              onClick={() => {
                onClear(fieldConfig.field);
                setAnchorEl(null);
              }}
            >
              清空
            </Button>
            {fieldConfig.mode === "text" ? (
              <>
                <TextField
                  select
                  label="匹配方式"
                  size="small"
                  value={operator === "equals" ? "equals" : "contains"}
                  onChange={(event) => setOperator(event.target.value as "contains" | "equals")}
                >
                  <MenuItem value="contains">包含</MenuItem>
                  <MenuItem value="equals">等于</MenuItem>
                </TextField>
                <TextField
                  autoFocus
                  label={`${fieldConfig.label}筛选值`}
                  size="small"
                  value={singleValue}
                  onChange={(event) => setSingleValue(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      applyValueFilter();
                    }
                  }}
                />
              </>
            ) : null}
            {fieldConfig.mode === "money" || fieldConfig.mode === "date" ? (
              <>
                <TextField
                  select
                  label="匹配方式"
                  size="small"
                  value={operator === "equals" ? "equals" : "between"}
                  onChange={(event) => setOperator(event.target.value as "between" | "equals")}
                >
                  <MenuItem value="between">区间</MenuItem>
                  <MenuItem value="equals">等于</MenuItem>
                </TextField>
                {operator === "equals" ? (
                  <TextField
                    autoFocus
                    label={`${fieldConfig.label}筛选值`}
                    size="small"
                    type={fieldConfig.mode === "date" ? "date" : "text"}
                    value={singleValue}
                    onChange={(event) => setSingleValue(event.target.value)}
                    InputLabelProps={fieldConfig.mode === "date" ? { shrink: true } : undefined}
                  />
                ) : (
                  <>
                    <TextField
                      autoFocus
                      label={fieldConfig.mode === "date" ? `${fieldConfig.label}开始日期` : `${fieldConfig.label}最小值`}
                      size="small"
                      type={fieldConfig.mode === "date" ? "date" : "text"}
                      value={minValue}
                      onChange={(event) => setMinValue(event.target.value)}
                      InputLabelProps={fieldConfig.mode === "date" ? { shrink: true } : undefined}
                    />
                    <TextField
                      label={fieldConfig.mode === "date" ? `${fieldConfig.label}结束日期` : `${fieldConfig.label}最大值`}
                      size="small"
                      type={fieldConfig.mode === "date" ? "date" : "text"}
                      value={maxValue}
                      onChange={(event) => setMaxValue(event.target.value)}
                      InputLabelProps={fieldConfig.mode === "date" ? { shrink: true } : undefined}
                    />
                  </>
                )}
              </>
            ) : null}
            <Button variant="contained" onClick={applyValueFilter}>
              应用筛选
            </Button>
          </Stack>
        ) : null}
      </Menu>
    </>
  );
}

function resolveSelectedValues(currentFilter?: OutputInvoiceCollectionFilterValue | null) {
  if (!currentFilter) {
    return [];
  }
  if ("values" in currentFilter && Array.isArray(currentFilter.values)) {
    return currentFilter.values;
  }
  if ("value" in currentFilter && typeof currentFilter.value === "string" && currentFilter.value) {
    return [currentFilter.value];
  }
  return [];
}
