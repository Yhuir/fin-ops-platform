import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import type { ReactNode } from "react";

type PageScaffoldProps = {
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
};

export default function PageScaffold({ title, description, actions, children, className }: PageScaffoldProps) {
  return (
    <Stack className={className ? `page-stack ${className}` : "page-stack"} spacing={2}>
      <Box component="header" className="page-header">
        <Box>
          <Typography component="h1" variant="h5" fontWeight={800}>
            {title}
          </Typography>
          {description ? (
            <Typography color="text.secondary" sx={{ mt: 0.75 }}>
              {description}
            </Typography>
          ) : null}
        </Box>
        {actions ? <Box className="page-header-actions">{actions}</Box> : null}
      </Box>
      {children}
    </Stack>
  );
}
