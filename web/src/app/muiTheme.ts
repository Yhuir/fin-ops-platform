import { createTheme } from "@mui/material/styles";
import type { zhCN as coreZhCN } from "@mui/material/locale";
import { zhCN } from "@mui/material/locale";
import { zhCN as dataGridZhCN } from "@mui/x-data-grid/locales";
import { zhCN as datePickersZhCN } from "@mui/x-date-pickers/locales";

const localeLayers: [typeof coreZhCN, typeof dataGridZhCN, typeof datePickersZhCN] = [
  zhCN,
  dataGridZhCN,
  datePickersZhCN,
];

export const muiTheme = createTheme(
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
    },
  },
  ...localeLayers,
);
