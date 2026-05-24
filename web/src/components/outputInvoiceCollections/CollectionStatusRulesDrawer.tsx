import CloseOutlinedIcon from "@mui/icons-material/CloseOutlined";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Divider from "@mui/material/Divider";
import Drawer from "@mui/material/Drawer";
import IconButton from "@mui/material/IconButton";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";
import { useEffect, useState } from "react";

import type { OutputInvoiceCollectionStatusRulesResponse } from "../../features/outputInvoiceCollections/types";

type CollectionStatusRulesDrawerProps = {
  open: boolean;
  loadRules: () => Promise<OutputInvoiceCollectionStatusRulesResponse>;
  onClose: () => void;
};

export default function CollectionStatusRulesDrawer({
  open,
  loadRules,
  onClose,
}: CollectionStatusRulesDrawerProps) {
  const [payload, setPayload] = useState<OutputInvoiceCollectionStatusRulesResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) {
      setPayload(null);
      setLoading(false);
      setError(null);
      return undefined;
    }
    let active = true;
    setLoading(true);
    setError(null);
    loadRules()
      .then((nextPayload) => {
        if (active) {
          setPayload(nextPayload);
        }
      })
      .catch((reason: unknown) => {
        if (active) {
          setError(reason instanceof Error ? reason.message : "收款状态规则加载失败");
        }
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, [loadRules, open]);

  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={onClose}
      transitionDuration={{ enter: 180, exit: 140 }}
      PaperProps={{
        "aria-label": open ? "销项发票收款情况类型设置" : undefined,
        sx: { width: { xs: "100%", sm: "min(900px, 58vw)" }, maxWidth: "100vw" },
      }}
    >
      <Stack sx={{ height: "100%" }}>
        <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ px: 2.5, py: 1.5 }}>
          <Box>
            <Typography component="h2" variant="h6" fontWeight={900}>销项发票收款情况类型设置</Typography>
            <Typography variant="caption" color="text.secondary">Sheet6 静态规则，只读展示</Typography>
          </Box>
          <IconButton aria-label="关闭销项发票收款情况类型设置" onClick={onClose}>
            <CloseOutlinedIcon />
          </IconButton>
        </Stack>
        <Divider />
        <Stack spacing={2} sx={{ flex: 1, minHeight: 0, overflow: "auto", p: 2.5 }}>
          {loading ? (
            <Stack direction="row" alignItems="center" spacing={1.25}>
              <CircularProgress aria-label="正在加载收款状态规则" size={22} />
              <Typography variant="body2" color="text.secondary">正在读取规则</Typography>
            </Stack>
          ) : null}
          {error ? <Alert severity="error">{error}</Alert> : null}
          {payload ? (
            <>
              <Stack direction="row" spacing={1} alignItems="center" useFlexGap flexWrap="wrap">
                {payload.version ? <Chip size="small" variant="outlined" label={`版本 ${payload.version}`} /> : null}
                <Chip size="small" color="info" variant="outlined" label="只读" />
              </Stack>
              <TableContainer component={Paper} variant="outlined">
                <Table size="small" aria-label="Sheet6 销项发票收款情况规则">
                  <TableHead>
                    <TableRow>
                      <TableCell>收款状态</TableCell>
                      <TableCell>识别方式</TableCell>
                      <TableCell>规则</TableCell>
                      <TableCell>必要事实</TableCell>
                      <TableCell>优先级</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {payload.rules.map((rule) => (
                      <TableRow key={rule.id || rule.code || rule.label}>
                        <TableCell sx={{ fontWeight: 900 }}>{rule.label}</TableCell>
                        <TableCell>{rule.recognitionMode || "未注明"}</TableCell>
                        <TableCell>
                          <Typography variant="body2">{rule.description}</Typography>
                          {rule.workbenchRequirement ? (
                            <Typography variant="caption" color="text.secondary">{rule.workbenchRequirement}</Typography>
                          ) : null}
                        </TableCell>
                        <TableCell>{(rule.requiredFacts ?? []).join(" / ") || "—"}</TableCell>
                        <TableCell>{rule.priority}</TableCell>
                      </TableRow>
                    ))}
                    {payload.rules.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={5}>暂无规则。</TableCell>
                      </TableRow>
                    ) : null}
                  </TableBody>
                </Table>
              </TableContainer>
              {payload.futureWriteBoundary ? (
                <Paper variant="outlined" sx={{ borderRadius: 1, p: 2 }}>
                  <Typography variant="subtitle2" fontWeight={900} sx={{ mb: 1 }}>
                    后续服务边界
                  </Typography>
                  {Object.entries(payload.futureWriteBoundary).map(([key, value]) => (
                    <Typography key={key} variant="body2" color="text.secondary">
                      {key}: {value}
                    </Typography>
                  ))}
                </Paper>
              ) : null}
            </>
          ) : null}
        </Stack>
      </Stack>
    </Drawer>
  );
}
