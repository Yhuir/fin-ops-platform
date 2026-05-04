import { createTheme } from "@mui/material/styles";
import type { SxProps, Theme } from "@mui/material/styles";
import type {} from "@mui/x-data-grid/themeAugmentation";

export const settingsTokens = {
  textPrimary: "#161616",
  textSecondary: "#525252",
  textMuted: "#6f6f6f",
  page: "#ffffff",
  layer01: "#f4f4f4",
  layer01Hover: "#e8e8e8",
  layer02: "#e0e0e0",
  borderSubtle: "#e0e0e0",
  borderDefault: "#c6c6c6",
  selected: "#edf5ff",
  primary: "#0f62fe",
  primaryHover: "#0043ce",
  primaryActive: "#002d9c",
  success: "#24a148",
  warning: "#f1c21b",
  error: "#da1e28",
};

export const settingsTheme = createTheme({
  palette: {
    primary: {
      main: settingsTokens.primary,
      dark: settingsTokens.primaryHover,
      contrastText: settingsTokens.page,
    },
    success: {
      main: settingsTokens.success,
    },
    warning: {
      main: settingsTokens.warning,
    },
    error: {
      main: settingsTokens.error,
    },
    text: {
      primary: settingsTokens.textPrimary,
      secondary: settingsTokens.textSecondary,
      disabled: settingsTokens.textMuted,
    },
    background: {
      default: settingsTokens.page,
      paper: settingsTokens.page,
    },
    divider: settingsTokens.borderSubtle,
    DataGrid: {
      bg: settingsTokens.page,
      pinnedBg: settingsTokens.layer01,
      headerBg: settingsTokens.layer01,
    },
  },
  shape: {
    borderRadius: 4,
  },
  spacing: 8,
  typography: {
    fontFamily: '"IBM Plex Sans", "Helvetica Neue", Arial, sans-serif',
    h4: {
      fontSize: "20px",
      fontWeight: 400,
      lineHeight: 1.4,
      letterSpacing: 0,
    },
    body2: {
      fontSize: "14px",
      lineHeight: 1.29,
      letterSpacing: "0.16px",
    },
    caption: {
      fontSize: "12px",
      lineHeight: 1.33,
      letterSpacing: "0.32px",
    },
    button: {
      textTransform: "none",
      letterSpacing: "0.16px",
      fontWeight: 400,
    },
  },
});

export const settingsPageSx: SxProps<Theme> = {
  display: "flex",
  flex: 1,
  minHeight: 0,
  flexDirection: "column",
  bgcolor: settingsTokens.page,
  overflow: "hidden",
};

export const settingsHeaderSx = {
  display: "flex",
  alignItems: { xs: "stretch", md: "center" },
  justifyContent: "space-between",
  flexDirection: { xs: "column", md: "row" },
  gap: 2,
  px: { xs: 2, md: 3 },
  py: 2,
  bgcolor: settingsTokens.page,
  borderBottom: `1px solid ${settingsTokens.borderSubtle}`,
} satisfies SxProps<Theme>;

export const settingsLayoutSx: SxProps<Theme> = {
  display: "grid",
  gridTemplateColumns: { xs: "minmax(0, 1fr)", md: "272px minmax(0, 1fr)" },
  flex: 1,
  minHeight: 0,
  bgcolor: settingsTokens.page,
};

export const settingsNavShellSx: SxProps<Theme> = {
  minWidth: 0,
  bgcolor: settingsTokens.layer01,
  borderRight: { md: `1px solid ${settingsTokens.borderSubtle}` },
  borderBottom: { xs: `1px solid ${settingsTokens.borderSubtle}`, md: 0 },
  p: { xs: 1.5, md: 2 },
};

export const settingsContentSx: SxProps<Theme> = {
  minWidth: 0,
  minHeight: 0,
  overflow: "auto",
  p: { xs: 2, md: 3 },
  bgcolor: settingsTokens.page,
  "& .settings-section-panel": {
    bgcolor: settingsTokens.page,
    border: `1px solid ${settingsTokens.borderSubtle}`,
    borderRadius: "4px",
    boxShadow: "none",
  },
  "& .settings-section-header": {
    borderBottom: `1px solid ${settingsTokens.borderSubtle}`,
  },
  "& .settings-section-header h3": {
    color: settingsTokens.textPrimary,
    fontSize: "16px",
    fontWeight: 400,
  },
  "& .settings-section-header span": {
    color: settingsTokens.textSecondary,
  },
};

export const settingsSectionSx = {
  bgcolor: settingsTokens.page,
  border: 0,
  borderRadius: 0,
  boxShadow: "none",
} satisfies SxProps<Theme>;

export const settingsDataGridSx = {
  border: `1px solid ${settingsTokens.borderSubtle}`,
  borderRadius: "4px",
  color: settingsTokens.textPrimary,
  "--DataGrid-overlayHeight": "240px",
  "& .MuiDataGrid-columnHeaders": {
    bgcolor: settingsTokens.layer01,
    borderBottom: `1px solid ${settingsTokens.borderDefault}`,
  },
  "& .MuiDataGrid-columnHeaderTitle": {
    color: settingsTokens.textPrimary,
    fontWeight: 600,
  },
  "& .MuiDataGrid-row:hover": {
    bgcolor: settingsTokens.layer01,
  },
  "& .MuiDataGrid-row.Mui-selected": {
    bgcolor: settingsTokens.selected,
  },
  "& .MuiDataGrid-cell": {
    borderColor: settingsTokens.borderSubtle,
  },
} satisfies SxProps<Theme>;

export const settingsButtonSx = {
  minHeight: 40,
  borderRadius: 0,
  px: 2,
  fontWeight: 400,
  bgcolor: settingsTokens.primary,
  color: settingsTokens.page,
  "&:hover": {
    bgcolor: settingsTokens.primaryHover,
  },
  "&:active": {
    bgcolor: settingsTokens.primaryActive,
  },
  "&.Mui-disabled": {
    bgcolor: settingsTokens.layer02,
    color: settingsTokens.textMuted,
  },
} satisfies SxProps<Theme>;
