import Stack from "@mui/material/Stack";
import type { ReactNode } from "react";

type PageToolbarProps = {
  left?: ReactNode;
  right?: ReactNode;
  children?: ReactNode;
  className?: string;
};

export default function PageToolbar({ left, right, children, className }: PageToolbarProps) {
  return (
    <Stack
      className={className}
      direction={{ xs: "column", md: "row" }}
      alignItems={{ xs: "stretch", md: "center" }}
      justifyContent="space-between"
      gap={1.5}
    >
      <Stack direction={{ xs: "column", sm: "row" }} gap={1} alignItems={{ xs: "stretch", sm: "center" }}>
        {left ?? children}
      </Stack>
      {right ? (
        <Stack direction={{ xs: "column", sm: "row" }} gap={1} alignItems={{ xs: "stretch", sm: "center" }}>
          {right}
        </Stack>
      ) : null}
    </Stack>
  );
}
