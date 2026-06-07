import CssBaseline from "@mui/material/CssBaseline";
import { zhCN } from "@mui/material/locale";
import { createTheme, ThemeProvider } from "@mui/material/styles";
import { AdapterDayjs } from "@mui/x-date-pickers/AdapterDayjs";
import { LocalizationProvider } from "@mui/x-date-pickers/LocalizationProvider";
import { zhCN as datePickersZhCN } from "@mui/x-date-pickers/locales";
import "dayjs/locale/zh-cn";
import type { ReactNode } from "react";

const legacyWorkbenchMuiTheme = createTheme(
  {
    palette: {
      mode: "light",
      primary: {
        main: "#1769aa",
        dark: "#0f4c81",
      },
      secondary: {
        main: "#2e7d32",
      },
      background: {
        default: "#f3f6fb",
        paper: "#ffffff",
      },
      text: {
        primary: "#243b53",
        secondary: "#486581",
      },
    },
    shape: {
      borderRadius: 8,
    },
    typography: {
      fontFamily: "\"SF Pro Text\", \"PingFang SC\", \"Microsoft YaHei\", sans-serif",
      button: {
        textTransform: "none",
        fontWeight: 700,
      },
    },
    components: {
      MuiButtonBase: {
        defaultProps: {
          disableRipple: true,
        },
      },
      MuiTooltip: {
        defaultProps: {
          arrow: true,
        },
      },
      MuiTableCell: {
        styleOverrides: {
          root: {
            textAlign: "center",
            verticalAlign: "middle",
          },
          head: {
            textAlign: "center",
            verticalAlign: "middle",
          },
          body: {
            textAlign: "center",
            verticalAlign: "middle",
          },
          alignLeft: {
            textAlign: "center",
          },
          alignRight: {
            textAlign: "center",
          },
          alignCenter: {
            textAlign: "center",
          },
        },
      },
    },
  },
  zhCN,
  datePickersZhCN,
);

export default function LegacyWorkbenchMuiProvider({ children }: { children: ReactNode }) {
  return (
    <ThemeProvider theme={legacyWorkbenchMuiTheme}>
      <LocalizationProvider dateAdapter={AdapterDayjs} adapterLocale="zh-cn">
        <CssBaseline />
        {children}
      </LocalizationProvider>
    </ThemeProvider>
  );
}
