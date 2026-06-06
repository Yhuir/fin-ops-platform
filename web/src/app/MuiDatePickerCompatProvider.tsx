import { LocalizationProvider } from "@mui/x-date-pickers/LocalizationProvider";
import { AdapterDayjs } from "@mui/x-date-pickers/AdapterDayjs";
import { zhCN as datePickersZhCN } from "@mui/x-date-pickers/locales";
import "dayjs/locale/zh-cn";
import type { ReactNode } from "react";

const datePickerLocaleText = datePickersZhCN.components.MuiLocalizationProvider.defaultProps.localeText;

export default function MuiDatePickerCompatProvider({ children }: { children: ReactNode }) {
  return (
    <LocalizationProvider dateAdapter={AdapterDayjs} adapterLocale="zh-cn" localeText={datePickerLocaleText}>
      {children}
    </LocalizationProvider>
  );
}
