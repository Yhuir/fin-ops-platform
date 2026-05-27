import { useEffect, useMemo, useState, type KeyboardEvent, type MouseEvent } from "react";
import AddIcon from "@mui/icons-material/Add";
import ArchiveIcon from "@mui/icons-material/Archive";
import ArrowDownwardIcon from "@mui/icons-material/ArrowDownward";
import ArrowUpwardIcon from "@mui/icons-material/ArrowUpward";
import CloseIcon from "@mui/icons-material/Close";
import ExpandLessIcon from "@mui/icons-material/ExpandLess";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import RestoreIcon from "@mui/icons-material/Restore";
import SaveIcon from "@mui/icons-material/Save";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Collapse from "@mui/material/Collapse";
import Divider from "@mui/material/Divider";
import Drawer from "@mui/material/Drawer";
import FormControl from "@mui/material/FormControl";
import IconButton from "@mui/material/IconButton";
import InputLabel from "@mui/material/InputLabel";
import ListItemText from "@mui/material/ListItemText";
import MenuItem from "@mui/material/MenuItem";
import OutlinedInput from "@mui/material/OutlinedInput";
import Paper from "@mui/material/Paper";
import Select from "@mui/material/Select";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Typography from "@mui/material/Typography";

import { fetchBankAutoTagRules, saveBankAutoTagRules } from "./api";
import type {
  BankAutoTagEditableRule,
  BankAutoTagRuleConditions,
  BankAutoTagRulesResponse,
  BankAutoTagSystemRule,
  SaveBankAutoTagRule,
} from "./types";

type AutoTagRulesDrawerProps = {
  open: boolean;
  onClose: () => void;
  onSaved?: (payload: BankAutoTagRulesResponse) => void;
};

type DraftRule = BankAutoTagEditableRule & { localId: string };

const EMPTY_RULES: BankAutoTagRuleConditions = {
  matchFields: ["all_text"],
  exact: [],
  contains: [],
  excludes: [],
};

function cloneRule(rule: BankAutoTagEditableRule, index: number): DraftRule {
  return {
    ...rule,
    localId: rule.code || `new-${index}`,
    rules: {
      matchFields: [...rule.rules.matchFields],
      exact: [...rule.rules.exact],
      contains: [...rule.rules.contains],
      excludes: [...rule.rules.excludes],
    },
  };
}

function linesToValues(value: string) {
  const seen = new Set<string>();
  return value
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter((item) => {
      if (!item || seen.has(item)) {
        return false;
      }
      seen.add(item);
      return true;
    });
}

function valuesToLines(values: string[]) {
  return values.join("\n");
}

function serializeRule(rule: DraftRule): SaveBankAutoTagRule {
  return {
    ...(rule.code ? { code: rule.code } : {}),
    label: rule.label.trim(),
    rules: {
      matchFields: [...rule.rules.matchFields],
      exact: [...rule.rules.exact],
      contains: [...rule.rules.contains],
      excludes: [...rule.rules.excludes],
    },
  };
}

function normalizedDraft(activeRules: DraftRule[], archivedRules: DraftRule[]) {
  return JSON.stringify({
    activeRules: activeRules.map(serializeRule),
    archivedRules: archivedRules.map(serializeRule),
  });
}

function ruleHasPositiveCondition(rule: DraftRule) {
  return rule.rules.exact.length > 0 || rule.rules.contains.length > 0;
}

function validateDraft(activeRules: DraftRule[]) {
  for (const [index, rule] of activeRules.entries()) {
    if (!rule.label.trim()) {
      return `优先级 ${index + 1} 的标签名称不能为空。`;
    }
    if (rule.rules.matchFields.length === 0) {
      return `${rule.label || `优先级 ${index + 1}`} 至少选择一个匹配字段。`;
    }
    if (!ruleHasPositiveCondition(rule)) {
      return `${rule.label || `优先级 ${index + 1}`} 需要填写精确命中字样或包含字样。`;
    }
  }
  return "";
}

function priorityLabel(index: number) {
  return `优先级 ${index + 1}`;
}

function summarizeTerms(label: string, values: string[]) {
  if (values.length === 0) {
    return `${label} 0`;
  }
  const preview = values.slice(0, 2).join("、");
  return values.length > 2 ? `${label} ${values.length}：${preview}…` : `${label}：${preview}`;
}

function summarizeFields(fields: string[], fieldOptions: BankAutoTagRulesResponse["fieldOptions"]) {
  if (fields.length === 0) {
    return "未选择匹配字段";
  }
  return fields
    .map((field) => fieldOptions.find((option) => option.value === field)?.label ?? field)
    .join("、");
}

function RuleSummaryItem({ label, value, tone = "default" }: { label: string; value: string; tone?: "default" | "warning" }) {
  return (
    <Box component="span" className={`bank-auto-tag-summary-item ${tone}`}>
      <Typography component="span" className="bank-auto-tag-summary-label" variant="caption">{label}</Typography>
      <Typography component="span" className="bank-auto-tag-summary-value" variant="caption">{value}</Typography>
    </Box>
  );
}

export default function AutoTagRulesDrawer({ open, onClose, onSaved }: AutoTagRulesDrawerProps) {
  const [tab, setTab] = useState<"active" | "archived">("active");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [version, setVersion] = useState(1);
  const [systemRule, setSystemRule] = useState<BankAutoTagSystemRule | null>(null);
  const [fieldOptions, setFieldOptions] = useState<BankAutoTagRulesResponse["fieldOptions"]>([]);
  const [canSave, setCanSave] = useState(true);
  const [activeRules, setActiveRules] = useState<DraftRule[]>([]);
  const [archivedRules, setArchivedRules] = useState<DraftRule[]>([]);
  const [baseline, setBaseline] = useState("");
  const [expandedRuleIds, setExpandedRuleIds] = useState<Set<string>>(() => new Set());

  useEffect(() => {
    if (!open) {
      return undefined;
    }
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    setFeedback(null);
    setTab("active");
    fetchBankAutoTagRules({ signal: controller.signal })
      .then((payload) => {
        const nextActive = payload.activeRules.map(cloneRule);
        const nextArchived = payload.archivedRules.map(cloneRule);
        setVersion(payload.version);
        setSystemRule(payload.systemRule);
        setFieldOptions(payload.fieldOptions);
        setCanSave(payload.permissions.canSave);
        setActiveRules(nextActive);
        setArchivedRules(nextArchived);
        setBaseline(normalizedDraft(nextActive, nextArchived));
        setExpandedRuleIds(new Set(nextActive.slice(0, 1).map((rule) => rule.localId)));
      })
      .catch((caught) => {
        if (!(caught instanceof DOMException && caught.name === "AbortError")) {
          setError(caught instanceof Error ? caught.message : "自动标签规则加载失败。");
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      });
    return () => controller.abort();
  }, [open]);

  const dirty = useMemo(() => normalizedDraft(activeRules, archivedRules) !== baseline, [activeRules, archivedRules, baseline]);

  const requestClose = () => {
    if (dirty && !window.confirm("自动标签规则有未保存修改，确定关闭吗？")) {
      return;
    }
    onClose();
  };

  const updateActiveRule = (localId: string, updater: (rule: DraftRule) => DraftRule) => {
    setActiveRules((current) => current.map((rule) => (rule.localId === localId ? updater(rule) : rule)));
  };

  const updateArchivedRule = (localId: string, updater: (rule: DraftRule) => DraftRule) => {
    setArchivedRules((current) => current.map((rule) => (rule.localId === localId ? updater(rule) : rule)));
  };

  const addRule = () => {
    const createdAt = Date.now();
    setActiveRules((current) => [
      ...current,
      {
        localId: `new-${createdAt}`,
        label: "",
        status: "active",
        source: "custom",
        rules: { ...EMPTY_RULES, matchFields: [...EMPTY_RULES.matchFields] },
        ruleSummary: "",
        editable: true,
        archivable: true,
        sortable: true,
      },
    ]);
    setTab("active");
    setExpandedRuleIds((current) => new Set(current).add(`new-${createdAt}`));
  };

  const moveRule = (localId: string, direction: -1 | 1) => {
    setActiveRules((current) => {
      const index = current.findIndex((rule) => rule.localId === localId);
      const nextIndex = index + direction;
      if (index < 0 || nextIndex < 0 || nextIndex >= current.length) {
        return current;
      }
      const next = [...current];
      const [rule] = next.splice(index, 1);
      next.splice(nextIndex, 0, rule);
      return next;
    });
  };

  const archiveRule = (localId: string) => {
    setActiveRules((current) => {
      const target = current.find((rule) => rule.localId === localId);
      if (!target) {
        return current;
      }
      setExpandedRuleIds((expanded) => {
        const next = new Set(expanded);
        next.delete(localId);
        return next;
      });
      setArchivedRules((archived) => [...archived, { ...target, status: "archived", priority: undefined, priorityLabel: undefined }]);
      return current.filter((rule) => rule.localId !== localId);
    });
  };

  const restoreRule = (localId: string) => {
    setArchivedRules((current) => {
      const target = current.find((rule) => rule.localId === localId);
      if (!target) {
        return current;
      }
      setActiveRules((active) => [...active, { ...target, status: "active" }]);
      setExpandedRuleIds((expanded) => new Set(expanded).add(target.localId));
      return current.filter((rule) => rule.localId !== localId);
    });
    setTab("active");
  };

  const toggleRuleExpanded = (localId: string) => {
    setExpandedRuleIds((current) => {
      const next = new Set(current);
      if (next.has(localId)) {
        next.delete(localId);
      } else {
        next.add(localId);
      }
      return next;
    });
  };

  const saveRules = () => {
    const validation = validateDraft(activeRules);
    if (validation) {
      setError(validation);
      return;
    }
    setSaving(true);
    setError(null);
    saveBankAutoTagRules({
      expectedVersion: version,
      activeRules: activeRules.map(serializeRule),
      archivedRules: archivedRules.map(serializeRule),
    })
      .then((payload) => {
        const nextActive = payload.activeRules.map(cloneRule);
        const nextArchived = payload.archivedRules.map(cloneRule);
        setVersion(payload.version);
        setSystemRule(payload.systemRule);
        setFieldOptions(payload.fieldOptions);
        setCanSave(payload.permissions.canSave);
        setActiveRules(nextActive);
        setArchivedRules(nextArchived);
        setBaseline(normalizedDraft(nextActive, nextArchived));
        setFeedback("规则已保存，银行明细正在刷新。");
        onSaved?.(payload);
      })
      .catch((caught) => {
        setError(caught instanceof Error ? caught.message : "自动标签规则保存失败。");
      })
      .finally(() => setSaving(false));
  };

  const readonly = !canSave || saving || loading;

  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={requestClose}
      transitionDuration={{ enter: 180, exit: 140 }}
      PaperProps={{
        "aria-label": open ? "自动标签规则" : undefined,
        className: "bank-auto-tag-drawer-paper",
        role: "dialog",
        sx: { width: { xs: "100%", sm: "60vw" }, maxWidth: "100vw" },
      }}
    >
      <Stack className="bank-auto-tag-drawer">
        <Stack className="bank-auto-tag-drawer-header" direction="row" alignItems="center" justifyContent="space-between">
          <Box>
            <Typography component="h2" variant="h6" fontWeight={900}>自动标签规则</Typography>
            <Typography variant="caption" color="text.secondary">
              版本 {version}{canSave ? "" : " · 只读"}
            </Typography>
          </Box>
          <IconButton aria-label="关闭自动标签规则抽屉" onClick={requestClose}>
            <CloseIcon />
          </IconButton>
        </Stack>
        <Divider />
        <Stack
          className="bank-auto-tag-drawer-toolbar"
          direction={{ xs: "column", sm: "row" }}
          alignItems={{ xs: "stretch", sm: "center" }}
          justifyContent="space-between"
          spacing={1.5}
        >
          <ToggleButtonGroup
            exclusive
            size="small"
            value={tab}
            onChange={(_event, value: "active" | "archived" | null) => {
              if (value) {
                setTab(value);
              }
            }}
            aria-label="自动标签规则状态"
          >
            <ToggleButton value="active">可用</ToggleButton>
            <ToggleButton value="archived">停用</ToggleButton>
          </ToggleButtonGroup>
          <Stack direction="row" spacing={1} justifyContent={{ xs: "flex-end", sm: "initial" }}>
            <Button startIcon={<AddIcon />} variant="outlined" size="small" onClick={addRule} disabled={readonly}>
              新增标签
            </Button>
            <Button startIcon={<SaveIcon />} variant="contained" size="small" onClick={saveRules} disabled={readonly || !dirty}>
              保存
            </Button>
          </Stack>
        </Stack>
        <Stack className="bank-auto-tag-rule-list" spacing={1.25}>
          {loading ? (
            <Stack direction="row" alignItems="center" spacing={1}>
              <CircularProgress size={20} />
              <Typography variant="body2" color="text.secondary">正在读取规则</Typography>
            </Stack>
          ) : null}
          {error ? <Alert severity="error">{error}</Alert> : null}
          {feedback ? <Alert severity="success">{feedback}</Alert> : null}
          {tab === "active" ? (
            <>
              {systemRule ? (
                <Paper className="bank-auto-tag-system-card" elevation={0}>
                  <Stack direction="row" alignItems="center" justifyContent="space-between" spacing={1.5}>
                    <Stack direction="row" alignItems="center" spacing={1} minWidth={0}>
                      <Chip size="small" variant="outlined" label={systemRule.priorityLabel} />
                      <Typography variant="subtitle2" fontWeight={900} noWrap>{systemRule.label}</Typography>
                      <Chip size="small" label="系统内置" />
                    </Stack>
                    <Typography variant="caption" color="text.secondary">固定优先命中</Typography>
                  </Stack>
                </Paper>
              ) : null}
              {activeRules.map((rule, index) => (
                <RuleEditor
                  key={rule.localId}
                  rule={rule}
                  priorityLabel={priorityLabel(index)}
                  fieldOptions={fieldOptions}
                  expanded={expandedRuleIds.has(rule.localId)}
                  disabled={readonly}
                  canMoveUp={index > 0}
                  canMoveDown={index < activeRules.length - 1}
                  onToggle={() => toggleRuleExpanded(rule.localId)}
                  onMoveUp={() => moveRule(rule.localId, -1)}
                  onMoveDown={() => moveRule(rule.localId, 1)}
                  onArchive={() => archiveRule(rule.localId)}
                  onChange={(updater) => updateActiveRule(rule.localId, updater)}
                />
              ))}
            </>
          ) : (
            <>
              {archivedRules.length === 0 ? <Alert severity="info">暂无停用标签。</Alert> : null}
              {archivedRules.map((rule) => (
                <Paper key={rule.localId} variant="outlined" sx={{ borderRadius: 1, p: 1.5 }}>
                  <Stack spacing={1}>
                    <Stack direction="row" justifyContent="space-between" spacing={1} alignItems="center">
                      <Stack direction="row" spacing={1} alignItems="center">
                        <Chip size="small" label="已停用" />
                        <Typography fontWeight={850}>{rule.label}</Typography>
                      </Stack>
                      <Button startIcon={<RestoreIcon />} size="small" onClick={() => restoreRule(rule.localId)} disabled={readonly}>
                        重新启用
                      </Button>
                    </Stack>
                    <Typography variant="body2" color="text.secondary">{rule.ruleSummary || "已停用"}</Typography>
                  </Stack>
                </Paper>
              ))}
            </>
          )}
        </Stack>
      </Stack>
    </Drawer>
  );
}

type RuleEditorProps = {
  rule: DraftRule;
  priorityLabel: string;
  fieldOptions: BankAutoTagRulesResponse["fieldOptions"];
  expanded: boolean;
  disabled: boolean;
  canMoveUp: boolean;
  canMoveDown: boolean;
  onToggle: () => void;
  onMoveUp: () => void;
  onMoveDown: () => void;
  onArchive: () => void;
  onChange: (updater: (rule: DraftRule) => DraftRule) => void;
};

function RuleEditor({
  rule,
  priorityLabel,
  fieldOptions,
  expanded,
  disabled,
  canMoveUp,
  canMoveDown,
  onToggle,
  onMoveUp,
  onMoveDown,
  onArchive,
  onChange,
}: RuleEditorProps) {
  const setRules = (patch: Partial<BankAutoTagRuleConditions>) => {
    onChange((current) => ({ ...current, rules: { ...current.rules, ...patch } }));
  };
  const title = rule.label.trim() || "未命名标签";
  const panelId = `${rule.localId}-editor-panel`;
  const stopHeaderAction = (event: MouseEvent) => {
    event.stopPropagation();
  };
  const handleHeaderKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onToggle();
    }
  };

  return (
    <Paper className={`bank-auto-tag-rule-card${expanded ? " expanded" : ""}`} elevation={0}>
      <Stack
        className="bank-auto-tag-rule-header"
        role="button"
        tabIndex={0}
        aria-expanded={expanded}
        aria-controls={panelId}
        onClick={onToggle}
        onKeyDown={handleHeaderKeyDown}
      >
        <Box className="bank-auto-tag-rule-header-main">
          <Stack className="bank-auto-tag-rule-title-row" direction="row" alignItems="center" spacing={1} minWidth={0}>
            <Chip size="small" color="primary" variant="outlined" label={priorityLabel} />
            <Typography component="h3" variant="subtitle1" fontWeight={900}>{title}</Typography>
            {rule.source === "custom" ? <Chip size="small" label="自定义" /> : null}
          </Stack>
          <Box className="bank-auto-tag-rule-summary">
            <RuleSummaryItem label="字段" value={summarizeFields(rule.rules.matchFields, fieldOptions)} />
            <RuleSummaryItem label="精确" value={summarizeTerms("", rule.rules.exact).replace(/^：|^ 0/, "0")} />
            <RuleSummaryItem label="包含" value={summarizeTerms("", rule.rules.contains).replace(/^：|^ 0/, "0")} />
            {rule.rules.excludes.length > 0 ? (
              <RuleSummaryItem label="排除" value={summarizeTerms("", rule.rules.excludes).replace(/^：|^ 0/, "0")} tone="warning" />
            ) : null}
          </Box>
        </Box>
        <Stack className="bank-auto-tag-rule-actions" direction="row" spacing={0.5} alignItems="center" onClick={stopHeaderAction}>
          <IconButton aria-label={`${title} 上移`} size="small" onClick={onMoveUp} disabled={disabled || !canMoveUp}>
            <ArrowUpwardIcon fontSize="small" />
          </IconButton>
          <IconButton aria-label={`${title} 下移`} size="small" onClick={onMoveDown} disabled={disabled || !canMoveDown}>
            <ArrowDownwardIcon fontSize="small" />
          </IconButton>
          <IconButton aria-label={`${title} 停用`} size="small" onClick={onArchive} disabled={disabled}>
            <ArchiveIcon fontSize="small" />
          </IconButton>
          <IconButton aria-label={`${expanded ? "收起" : "展开"} ${title}`} size="small" onClick={onToggle}>
            {expanded ? <ExpandLessIcon fontSize="small" /> : <ExpandMoreIcon fontSize="small" />}
          </IconButton>
        </Stack>
      </Stack>
      <Collapse in={expanded} timeout="auto" unmountOnExit>
        <Box id={panelId} className="bank-auto-tag-rule-editor">
          <Box className="bank-auto-tag-rule-editor-body">
            <TextField
              className="bank-auto-tag-rule-name-field"
              label="标签名称"
              size="small"
              value={rule.label}
              onChange={(event) => onChange((current) => ({ ...current, label: event.target.value }))}
              disabled={disabled}
            />
            <FormControl className="bank-auto-tag-rule-field-picker" size="small" disabled={disabled}>
              <InputLabel id={`${rule.localId}-fields-label`}>匹配字段</InputLabel>
              <Select
                labelId={`${rule.localId}-fields-label`}
                multiple
                value={rule.rules.matchFields}
                input={<OutlinedInput label="匹配字段" />}
                renderValue={(selected) => selected.map((value) => fieldOptions.find((option) => option.value === value)?.label ?? value).join("、")}
                onChange={(event) => {
                  const value = event.target.value;
                  setRules({ matchFields: typeof value === "string" ? value.split(",") : value });
                }}
              >
                {fieldOptions.map((option) => (
                  <MenuItem key={option.value} value={option.value}>
                    <Checkbox checked={rule.rules.matchFields.includes(option.value)} />
                    <ListItemText primary={option.label} />
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          </Box>
          <Box className="bank-auto-tag-condition-grid">
            <TextField
              className="bank-auto-tag-condition-field"
              label="精确命中字样"
              value={valuesToLines(rule.rules.exact)}
              onChange={(event) => setRules({ exact: linesToValues(event.target.value) })}
              disabled={disabled}
              multiline
              minRows={3}
              fullWidth
              helperText="一行一个完整匹配文本"
            />
            <TextField
              className="bank-auto-tag-condition-field"
              label="包含字样"
              value={valuesToLines(rule.rules.contains)}
              onChange={(event) => setRules({ contains: linesToValues(event.target.value) })}
              disabled={disabled}
              multiline
              minRows={3}
              fullWidth
              helperText="任意一行命中即可"
            />
            <TextField
              className="bank-auto-tag-condition-field"
              label="不包含字样"
              value={valuesToLines(rule.rules.excludes)}
              onChange={(event) => setRules({ excludes: linesToValues(event.target.value) })}
              disabled={disabled}
              multiline
              minRows={3}
              fullWidth
              helperText="命中后排除该规则"
            />
          </Box>
        </Box>
      </Collapse>
    </Paper>
  );
}
