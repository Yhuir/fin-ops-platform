import Box from "@mui/material/Box";
import type { SxProps, Theme } from "@mui/material/styles";
import { DatePicker } from "@mui/x-date-pickers/DatePicker";
import { StaticDatePicker } from "@mui/x-date-pickers/StaticDatePicker";
import dayjs, { type Dayjs } from "dayjs";

type MonthPickerProps = {
  value: string;
  onChange: (month: string) => void;
  ariaLabel?: string;
  caption?: string | null;
  inline?: boolean;
};

function parseMonthValue(value: string) {
  const [yearText, monthText] = value.split("-");
  const year = Number.parseInt(yearText, 10);
  const month = Number.parseInt(monthText, 10);
  return {
    year: Number.isFinite(year) ? year : 2026,
    month: Number.isFinite(month) ? month : 1,
  };
}

function toPickerValue(value: string) {
  const { year, month } = parseMonthValue(value);
  return dayjs(`${year}-${String(month).padStart(2, "0")}-01`);
}

function emitMonth(nextValue: Dayjs | null, onChange: (month: string) => void) {
  if (!nextValue?.isValid()) {
    return;
  }
  onChange(nextValue.format("YYYY-MM"));
}

export function formatMonthLabel(value: string) {
  const { year, month } = parseMonthValue(value);
  return `${year}年${month}月`;
}

const pickerSx: SxProps<Theme> = {
  minWidth: 168,
  "& .MuiInputBase-root": {
    backgroundColor: "background.paper",
  },
};

export default function MonthPicker({
  value,
  onChange,
  ariaLabel = "年月选择",
  caption = "月份",
  inline = false,
}: MonthPickerProps) {
  const pickerValue = toPickerValue(value);
  const label = caption ?? ariaLabel;

  if (inline) {
    return (
      <Box className="month-picker month-picker-mui-inline">
        <StaticDatePicker
          aria-label={ariaLabel}
          displayStaticWrapperAs="desktop"
          openTo="month"
          reduceAnimations
          value={pickerValue}
          views={["year", "month"]}
          onChange={(nextValue) => emitMonth(nextValue, onChange)}
          slotProps={{
            actionBar: { actions: [] },
            toolbar: { hidden: true },
          }}
        />
      </Box>
    );
  }

  return (
    <Box className="month-picker month-picker-mui">
      <DatePicker
        closeOnSelect
        format="YYYY年MM月"
        label={label}
        openTo="year"
        reduceAnimations
        value={pickerValue}
        views={["year", "month"]}
        onChange={(nextValue) => emitMonth(nextValue, onChange)}
        slotProps={{
          openPickerButton: {
            "aria-label": ariaLabel,
          },
          textField: {
            size: "small",
            sx: pickerSx,
          },
        }}
      />
    </Box>
  );
}
