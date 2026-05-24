import ExpandLessOutlinedIcon from "@mui/icons-material/ExpandLessOutlined";
import ExpandMoreOutlinedIcon from "@mui/icons-material/ExpandMoreOutlined";
import Box from "@mui/material/Box";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";

type ExpandableCellTextProps = {
  text: string;
  expanded: boolean;
  onToggle: () => void;
  title?: string;
  threshold?: number;
};

function previewLabel(text: string) {
  return text.length > 28 ? `${text.slice(0, 28)}...` : text;
}

export default function ExpandableCellText({
  text,
  expanded,
  onToggle,
  title,
  threshold = 26,
}: ExpandableCellTextProps) {
  const value = text || "—";
  const canExpand = value.length > threshold;
  return (
    <Stack direction="row" spacing={0.25} alignItems="flex-start" sx={{ minWidth: 0 }}>
      <Typography
        component="div"
        variant="body2"
        title={title ?? value}
        sx={{
          minWidth: 0,
          overflowWrap: "anywhere",
          ...(expanded || !canExpand
            ? {}
            : {
              display: "-webkit-box",
              WebkitBoxOrient: "vertical",
              WebkitLineClamp: 2,
              overflow: "hidden",
            }),
        }}
      >
        {value}
      </Typography>
      {canExpand ? (
        <Box component="span" sx={{ flexShrink: 0, mt: -0.5 }}>
          <Tooltip title={expanded ? "收起" : "展开"}>
            <IconButton
              aria-label={`${expanded ? "收起" : "展开"} ${previewLabel(value)}`}
              size="small"
              onClick={onToggle}
            >
              {expanded ? <ExpandLessOutlinedIcon fontSize="inherit" /> : <ExpandMoreOutlinedIcon fontSize="inherit" />}
            </IconButton>
          </Tooltip>
        </Box>
      ) : null}
    </Stack>
  );
}
