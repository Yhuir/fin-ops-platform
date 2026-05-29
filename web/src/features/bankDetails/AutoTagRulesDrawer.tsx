import { useEffect, useMemo, useState } from "react";
import AddIcon from "@mui/icons-material/Add";
import CloseIcon from "@mui/icons-material/Close";
import DeleteIcon from "@mui/icons-material/Delete";
import RestoreIcon from "@mui/icons-material/Restore";
import SaveIcon from "@mui/icons-material/Save";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogContentText from "@mui/material/DialogContentText";
import DialogTitle from "@mui/material/DialogTitle";
import Divider from "@mui/material/Divider";
import Drawer from "@mui/material/Drawer";
import FormControl from "@mui/material/FormControl";
import IconButton from "@mui/material/IconButton";
import ListItemText from "@mui/material/ListItemText";
import MenuItem from "@mui/material/MenuItem";
import Paper from "@mui/material/Paper";
import Select from "@mui/material/Select";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import TextField from "@mui/material/TextField";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";

import { fetchBankAutoTagRules, saveBankAutoTagRules } from "./api";
import type {
  BankAutoTagDirection,
  BankAutoTagEditableRule,
  BankAutoTagRuleConditions,
  BankAutoTagRefreshScope,
  BankAutoTagRulesResponse,
  BankAutoTagSystemRule,
  SaveBankAutoTagRule,
} from "./types";

type AutoTagRulesDrawerProps = {
  open: boolean;
  onClose: () => void;
  onSaved?: (payload: BankAutoTagRulesResponse) => void;
  refreshStatus?: "idle" | "refreshing" | "fresh";
  refreshScope?: BankAutoTagRefreshScope;
};

type DraftRule = BankAutoTagEditableRule & { localId: string };
type RuleConditionKey = "containsAny" | "containsAll" | "exactAny" | "noneOf";
type RuleGroup = {
  key: string;
  primaryLabel: string;
  colorClass: string;
  rules: DraftRule[];
};

const EMPTY_RULES: BankAutoTagRuleConditions = {
  matchFields: ["all_text"],
  exactAny: [],
  containsAny: [],
  containsAll: [],
  noneOf: [],
  regexAny: [],
};

const DIRECTION_OPTIONS: { value: BankAutoTagDirection; label: string }[] = [
  { value: "any", label: "不限" },
  { value: "income", label: "收入" },
  { value: "expense", label: "支出" },
];

const HIDDEN_MATCH_FIELDS = new Set(["all_text"]);
const GROUP_COLOR_CLASSES = [
  "bank-auto-tag-group-blue",
  "bank-auto-tag-group-teal",
  "bank-auto-tag-group-green",
  "bank-auto-tag-group-amber",
  "bank-auto-tag-group-violet",
  "bank-auto-tag-group-rose",
];

function cloneRule(rule: BankAutoTagEditableRule, index: number): DraftRule {
  const sortOrder = typeof rule.sortOrder === "number" ? rule.sortOrder : index + 1;
  return {
    ...rule,
    priority: 2,
    sortOrder,
    localId: rule.code || `new-${index}`,
    accountScope: { type: "any", values: [] },
    rules: {
      matchFields: [...rule.rules.matchFields],
      exactAny: [...rule.rules.exactAny],
      containsAny: [...rule.rules.containsAny],
      containsAll: [...rule.rules.containsAll],
      noneOf: [...rule.rules.noneOf],
      regexAny: [],
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
  const outputPrimaryLabel = rule.outputPrimaryLabel.trim();
  const outputSubLabel = rule.outputSubLabel.trim();
  const label = outputSubLabel || outputPrimaryLabel;
  return {
    ...(rule.code ? { code: rule.code } : {}),
    label,
    priority: 2,
    ...(typeof rule.sortOrder === "number" ? { sortOrder: rule.sortOrder } : {}),
    outputPrimaryLabel,
    outputSubLabel,
    direction: rule.direction,
    accountScope: { type: "any", values: [] },
    rules: {
      matchFields: [...rule.rules.matchFields],
      exactAny: [...rule.rules.exactAny],
      containsAny: [...rule.rules.containsAny],
      containsAll: [...rule.rules.containsAll],
      noneOf: [...rule.rules.noneOf],
      regexAny: [],
    },
  };
}

function normalizedDraft(activeRules: DraftRule[], archivedRules: DraftRule[]) {
  return JSON.stringify({
    activeRules: activeRules.map(serializeRule),
    archivedRules: archivedRules.map(serializeRule),
  });
}

function normalizeRulePriority(value: unknown) {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed >= 2 ? parsed : 2;
}

function ruleHasPositiveCondition(rule: DraftRule) {
  return rule.rules.exactAny.length > 0 || rule.rules.containsAny.length > 0 || rule.rules.containsAll.length > 0;
}

function validateDraft(activeRules: DraftRule[]) {
  const seenLabelPaths = new Map<string, number>();
  for (const [index, rule] of activeRules.entries()) {
    const outputPrimaryLabel = rule.outputPrimaryLabel.trim();
    const outputSubLabel = rule.outputSubLabel.trim();
    if (!outputPrimaryLabel) {
      return `第 ${index + 1} 条规则的主标签名称不能为空。`;
    }
    if (!Number.isInteger(rule.priority) || Number(rule.priority) < 2) {
      return `${outputPrimaryLabel} 的普通规则优先级必须是大于等于 2 的整数。`;
    }
    const labelPathKey = `${outputPrimaryLabel}\u0000${outputSubLabel}`;
    if (seenLabelPaths.has(labelPathKey)) {
      return `${outputSubLabel ? `${outputPrimaryLabel} / ${outputSubLabel}` : outputPrimaryLabel} 的主标签名称和子标签名称组合不能重复。`;
    }
    seenLabelPaths.set(labelPathKey, index);
    if (rule.rules.matchFields.length === 0) {
      return `${outputPrimaryLabel} 至少选择一个匹配字段。`;
    }
    if (!ruleHasPositiveCondition(rule)) {
      return `${outputPrimaryLabel} 需要填写精准命中、包含或必须同时包含。`;
    }
  }
  return "";
}

function ruleDisplayLabel(rule: Pick<DraftRule, "label" | "outputPrimaryLabel" | "outputSubLabel">) {
  const primary = rule.outputPrimaryLabel.trim();
  const sub = rule.outputSubLabel.trim();
  if (primary && sub) {
    return `${primary} / ${sub}`;
  }
  return primary || rule.label.trim() || "未命名标签";
}

function conditionDisplay(values: string[]) {
  return values.length ? values : ["无"];
}

function fieldLabels(values: string[], fieldOptions: BankAutoTagRulesResponse["fieldOptions"]) {
  const labels = values
    .filter((value) => !HIDDEN_MATCH_FIELDS.has(value))
    .map((value) => fieldOptions.find((option) => option.value === value)?.label ?? value);
  return labels.length ? labels.join("、") : "未选择";
}

function groupRules(rules: DraftRule[]): RuleGroup[] {
  const groups: RuleGroup[] = [];
  const byKey = new Map<string, RuleGroup>();
  const sortedRules = [...rules].sort((left, right) => (
    normalizeRulePriority(left.priority) - normalizeRulePriority(right.priority)
    || Number(left.sortOrder ?? 10_000) - Number(right.sortOrder ?? 10_000)
    || String(left.code ?? left.localId).localeCompare(String(right.code ?? right.localId), "zh-Hans-CN")
  ));
  for (const rule of sortedRules) {
    const primaryLabel = rule.outputPrimaryLabel.trim() || "未命名主标签";
    const key = primaryLabel;
    let group = byKey.get(key);
    if (!group) {
      group = {
        key,
        primaryLabel,
        colorClass: GROUP_COLOR_CLASSES[groups.length % GROUP_COLOR_CLASSES.length],
        rules: [],
      };
      byKey.set(key, group);
      groups.push(group);
    }
    group.rules.push(rule);
  }
  return groups;
}

export default function AutoTagRulesDrawer({ open, onClose, onSaved, refreshStatus = "idle", refreshScope }: AutoTagRulesDrawerProps) {
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
  const [conditionEditor, setConditionEditor] = useState<{
    localId: string;
    key: RuleConditionKey;
    label: string;
    values: string[];
  } | null>(null);
  const [pendingArchiveRule, setPendingArchiveRule] = useState<DraftRule | null>(null);

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

  useEffect(() => {
    if (refreshStatus === "refreshing") {
      setFeedback("规则已保存，银行明细正在刷新。");
    }
    if (refreshStatus === "fresh") {
      setFeedback("规则已保存，银行明细已刷新。");
    }
  }, [refreshStatus]);

  const dirty = useMemo(() => normalizedDraft(activeRules, archivedRules) !== baseline, [activeRules, archivedRules, baseline]);
  const readonly = !canSave || saving || loading;
  const visibleFieldOptions = fieldOptions.filter((option) => !HIDDEN_MATCH_FIELDS.has(option.value));
  const activeRuleGroups = useMemo(() => groupRules(activeRules), [activeRules]);

  const requestClose = () => {
    if (dirty && !window.confirm("自动标签规则有未保存修改，确定关闭吗？")) {
      return;
    }
    onClose();
  };

  const updateActiveRule = (localId: string, updater: (rule: DraftRule) => DraftRule) => {
    setActiveRules((current) => current.map((rule) => (rule.localId === localId ? updater(rule) : rule)));
  };

  const updateGroupPrimaryLabel = (group: RuleGroup, value: string) => {
    const localIds = new Set(group.rules.map((rule) => rule.localId));
    setActiveRules((current) => current.map((rule) => (
      localIds.has(rule.localId) ? { ...rule, outputPrimaryLabel: value } : rule
    )));
  };

  const addRule = () => {
    const createdAt = Date.now();
    setActiveRules((current) => [
      ...current,
      {
        localId: `new-${createdAt}`,
        label: "",
        outputPrimaryLabel: "",
        outputSubLabel: "",
        status: "active",
        source: "custom",
        priority: 2,
        priorityLabel: "优先级 2",
        sortOrder: current.length + archivedRules.length + 1,
        direction: "any",
        accountScope: { type: "any", values: [] },
        rules: { ...EMPTY_RULES, matchFields: ["purpose_text", "summary_text", "note_text", "detail_text"] },
        ruleSummary: "",
        editable: true,
        archivable: true,
        sortable: true,
      },
    ]);
    setTab("active");
  };

  const archiveRule = (localId: string) => {
    setActiveRules((current) => {
      const target = current.find((rule) => rule.localId === localId);
      if (!target) {
        return current;
      }
      if (target.code) {
        setArchivedRules((archived) => [
          ...archived.filter((rule) => rule.code !== target.code),
          { ...target, status: "archived" },
        ]);
      }
      return current.filter((rule) => rule.localId !== localId);
    });
  };

  const restoreRule = (localId: string) => {
    setArchivedRules((current) => {
      const target = current.find((rule) => rule.localId === localId);
      if (!target) {
        return current;
      }
      setActiveRules((active) => [...active, { ...target, status: "active", priority: 2 }]);
      return current.filter((rule) => rule.localId !== localId);
    });
    setTab("active");
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
      refreshScope,
      activeRules: activeRules.map(serializeRule),
      archivedRules: archivedRules.filter((rule) => rule.code).map(serializeRule),
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
        setFeedback(payload.readModelStatus === "fresh" ? "规则已保存，银行明细已刷新。" : "规则已保存，银行明细正在刷新。");
        onSaved?.(payload);
      })
      .catch((caught) => {
        setError(caught instanceof Error ? caught.message : "自动标签规则保存失败。");
      })
      .finally(() => setSaving(false));
  };

  const commitConditionEditor = () => {
    if (!conditionEditor) {
      return;
    }
    const values = conditionEditor.values;
    updateActiveRule(conditionEditor.localId, (rule) => ({
      ...rule,
      rules: { ...rule.rules, [conditionEditor.key]: values },
    }));
    setConditionEditor(null);
  };

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
        sx: { width: "80vw", maxWidth: "80vw" },
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
        <Stack className="bank-auto-tag-table-shell" spacing={1.25}>
          {loading ? (
            <Stack direction="row" alignItems="center" spacing={1}>
              <CircularProgress size={20} />
              <Typography variant="body2" color="text.secondary">正在读取规则</Typography>
            </Stack>
          ) : null}
          {error ? <Alert severity="error">{error}</Alert> : null}
          {feedback ? <Alert severity="success">{feedback}</Alert> : null}
          {tab === "active" ? (
            <TableContainer component={Paper} variant="outlined" className="bank-auto-tag-table-container">
              <Table stickyHeader size="small" className="bank-auto-tag-rule-table" aria-label="自动标签规则表格">
                <colgroup>
                  <col className="bank-auto-tag-col-primary" />
                  <col className="bank-auto-tag-col-sub" />
                  <col className="bank-auto-tag-col-direction" />
                  <col className="bank-auto-tag-col-fields" />
                  <col className="bank-auto-tag-col-contains" />
                  <col className="bank-auto-tag-col-contains-all" />
                  <col className="bank-auto-tag-col-exact" />
                  <col className="bank-auto-tag-col-none" />
                  <col className="bank-auto-tag-col-priority" />
                  <col className="bank-auto-tag-col-actions" />
                </colgroup>
                <TableHead>
                  <TableRow>
                    <TableCell>主标签</TableCell>
                    <TableCell>子标签</TableCell>
                    <TableCell>流水类型</TableCell>
                    <TableCell>查询项</TableCell>
                    <TableCell>包含</TableCell>
                    <TableCell>必须同时包含</TableCell>
                    <TableCell>精准命中</TableCell>
                    <TableCell>不包含字样</TableCell>
                    <TableCell>优先级</TableCell>
                    <TableCell align="right">操作</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {systemRule ? (
                    <TableRow className="bank-auto-tag-system-row">
                      <TableCell>{systemRule.label}</TableCell>
                      <TableCell>系统规则</TableCell>
                      <TableCell>不限</TableCell>
                      <TableCell>—</TableCell>
                      <TableCell>—</TableCell>
                      <TableCell>—</TableCell>
                      <TableCell>—</TableCell>
                      <TableCell>—</TableCell>
                      <TableCell>1</TableCell>
                      <TableCell align="right">—</TableCell>
                    </TableRow>
                  ) : null}
                  {activeRuleGroups.flatMap((group) => group.rules.map((rule, rowIndex) => (
                    <TableRow key={rule.localId} className={`bank-auto-tag-rule-row ${group.colorClass}`}>
                      {rowIndex === 0 ? (
                        <TableCell
                          rowSpan={group.rules.length}
                          className={`bank-auto-tag-primary-cell ${group.colorClass}`}
                        >
                          <TextField
                            variant="standard"
                            size="small"
                            placeholder="主标签名称"
                            value={group.primaryLabel === "未命名主标签" ? "" : group.primaryLabel}
                            disabled={readonly}
                            inputProps={{ "aria-label": `${group.primaryLabel} 主标签` }}
                            onChange={(event) => updateGroupPrimaryLabel(group, event.target.value)}
                          />
                        </TableCell>
                      ) : null}
                      <TableCell>
                        <TextField
                          variant="standard"
                          size="small"
                          placeholder="子标签名称"
                          value={rule.outputSubLabel}
                          disabled={readonly}
                          inputProps={{ "aria-label": `${ruleDisplayLabel(rule)} 子标签` }}
                          onChange={(event) => updateActiveRule(rule.localId, (current) => ({
                            ...current,
                            outputSubLabel: event.target.value,
                          }))}
                        />
                      </TableCell>
                      <TableCell>
                        <Select
                          variant="standard"
                          size="small"
                          value={rule.direction}
                          disabled={readonly}
                          aria-label={`${ruleDisplayLabel(rule)} 流水类型`}
                          inputProps={{ "aria-label": `${ruleDisplayLabel(rule)} 流水类型` }}
                          onChange={(event) => updateActiveRule(rule.localId, (current) => ({
                            ...current,
                            direction: event.target.value as BankAutoTagDirection,
                          }))}
                        >
                          {DIRECTION_OPTIONS.map((option) => (
                            <MenuItem key={option.value} value={option.value}>{option.label}</MenuItem>
                          ))}
                        </Select>
                      </TableCell>
                      <TableCell>
                        <FormControl size="small" fullWidth disabled={readonly} variant="standard">
                          <Select
                            variant="standard"
                            multiple
                            displayEmpty
                            aria-label={`${ruleDisplayLabel(rule)} 查询项`}
                            inputProps={{ "aria-label": `${ruleDisplayLabel(rule)} 查询项` }}
                            value={rule.rules.matchFields.filter((field) => !HIDDEN_MATCH_FIELDS.has(field))}
                            renderValue={(selected) => fieldLabels(selected, fieldOptions)}
                            onChange={(event) => {
                              const value = event.target.value;
                              const selectedValues = (typeof value === "string" ? value.split(",") : value)
                                .map((item) => String(item || "").trim())
                                .filter((item) => item && !HIDDEN_MATCH_FIELDS.has(item));
                              updateActiveRule(rule.localId, (current) => ({
                                ...current,
                                rules: { ...current.rules, matchFields: selectedValues },
                              }));
                            }}
                          >
                            <Box className="bank-auto-tag-field-menu-actions" onMouseDown={(event) => event.preventDefault()}>
                              <Button
                                size="small"
                                disabled={readonly}
                                onClick={(event) => {
                                  event.stopPropagation();
                                  updateActiveRule(rule.localId, (current) => ({
                                    ...current,
                                    rules: { ...current.rules, matchFields: visibleFieldOptions.map((option) => option.value) },
                                  }));
                                }}
                              >
                                全选
                              </Button>
                              <Button
                                size="small"
                                color="inherit"
                                disabled={readonly}
                                onClick={(event) => {
                                  event.stopPropagation();
                                  updateActiveRule(rule.localId, (current) => ({
                                    ...current,
                                    rules: { ...current.rules, matchFields: [] },
                                  }));
                                }}
                              >
                                清空
                              </Button>
                            </Box>
                            {visibleFieldOptions.map((option) => (
                              <MenuItem key={option.value} value={option.value}>
                                <Checkbox checked={rule.rules.matchFields.includes(option.value)} />
                                <ListItemText primary={option.label} />
                              </MenuItem>
                            ))}
                          </Select>
                        </FormControl>
                      </TableCell>
                      <ConditionCell
                        ruleLabel={ruleDisplayLabel(rule)}
                        label="包含"
                        values={rule.rules.containsAny}
                        disabled={readonly}
                        onEdit={() => setConditionEditor({ localId: rule.localId, key: "containsAny", label: "包含", values: rule.rules.containsAny })}
                      />
                      <ConditionCell
                        ruleLabel={ruleDisplayLabel(rule)}
                        label="必须同时包含"
                        values={rule.rules.containsAll}
                        disabled={readonly}
                        onEdit={() => setConditionEditor({ localId: rule.localId, key: "containsAll", label: "必须同时包含", values: rule.rules.containsAll })}
                      />
                      <ConditionCell
                        ruleLabel={ruleDisplayLabel(rule)}
                        label="精准命中"
                        values={rule.rules.exactAny}
                        disabled={readonly}
                        onEdit={() => setConditionEditor({ localId: rule.localId, key: "exactAny", label: "精准命中", values: rule.rules.exactAny })}
                      />
                      <ConditionCell
                        ruleLabel={ruleDisplayLabel(rule)}
                        label="不包含字样"
                        values={rule.rules.noneOf}
                        disabled={readonly}
                        onEdit={() => setConditionEditor({ localId: rule.localId, key: "noneOf", label: "不包含字样", values: rule.rules.noneOf })}
                      />
                      <TableCell className="bank-auto-tag-priority-cell">
                        <Typography component="span" className="bank-auto-tag-priority-value" aria-label={`${ruleDisplayLabel(rule)} 优先级`}>
                          2
                        </Typography>
                      </TableCell>
                      <TableCell align="right">
                        <Stack direction="row" justifyContent="flex-end" spacing={0.5}>
                          <Tooltip title="停用">
                            <span>
                              <IconButton
                                size="small"
                                aria-label={`停用 ${ruleDisplayLabel(rule)}`}
                                disabled={readonly}
                                onClick={() => setPendingArchiveRule(rule)}
                              >
                                <DeleteIcon fontSize="small" />
                              </IconButton>
                            </span>
                          </Tooltip>
                        </Stack>
                      </TableCell>
                    </TableRow>
                  )))}
                </TableBody>
              </Table>
            </TableContainer>
          ) : (
            <Stack spacing={1}>
              {archivedRules.length === 0 ? <Alert severity="info">暂无停用标签。</Alert> : null}
              {archivedRules.map((rule) => (
                <Paper key={rule.localId} variant="outlined" sx={{ borderRadius: 1, p: 1.5 }}>
                  <Stack direction="row" justifyContent="space-between" spacing={1} alignItems="center">
                    <Stack direction="row" spacing={1} alignItems="center" minWidth={0}>
                      <Chip size="small" label="已停用" />
                      <Typography fontWeight={850} noWrap>{ruleDisplayLabel(rule)}</Typography>
                    </Stack>
                    <Button startIcon={<RestoreIcon />} size="small" onClick={() => restoreRule(rule.localId)} disabled={readonly}>
                      重新启用
                    </Button>
                  </Stack>
                </Paper>
              ))}
            </Stack>
          )}
        </Stack>
      </Stack>
      <Dialog open={conditionEditor !== null} onClose={() => setConditionEditor(null)} maxWidth="sm" fullWidth>
        <DialogTitle>{conditionEditor?.label}</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            multiline
            minRows={10}
            fullWidth
            margin="dense"
            value={valuesToLines(conditionEditor?.values ?? [])}
            onChange={(event) => setConditionEditor((current) => current ? {
              ...current,
              values: linesToValues(event.target.value),
            } : current)}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConditionEditor(null)}>取消</Button>
          <Button variant="contained" onClick={commitConditionEditor}>确定</Button>
        </DialogActions>
      </Dialog>
      <Dialog
        open={pendingArchiveRule !== null}
        onClose={() => setPendingArchiveRule(null)}
        aria-labelledby="bank-auto-tag-archive-dialog-title"
      >
        <DialogTitle id="bank-auto-tag-archive-dialog-title">确认停用标签</DialogTitle>
        <DialogContent>
          <DialogContentText>
            {pendingArchiveRule ? `确定停用「${ruleDisplayLabel(pendingArchiveRule)}」吗？` : ""}
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setPendingArchiveRule(null)}>取消</Button>
          <Button
            color="error"
            variant="contained"
            onClick={() => {
              if (pendingArchiveRule) {
                archiveRule(pendingArchiveRule.localId);
              }
              setPendingArchiveRule(null);
            }}
          >
            确认停用
          </Button>
        </DialogActions>
      </Dialog>
    </Drawer>
  );
}

function ConditionCell({
  ruleLabel,
  label,
  values,
  disabled,
  onEdit,
}: {
  ruleLabel: string;
  label: string;
  values: string[];
  disabled: boolean;
  onEdit: () => void;
}) {
  return (
    <TableCell>
      <Button
        className="bank-auto-tag-condition-field-button"
        size="small"
        variant="outlined"
        aria-label={`编辑${ruleLabel}${label}`}
        disabled={disabled}
        onClick={onEdit}
      >
        <Stack className="bank-auto-tag-condition-preview" spacing={0.25}>
          {conditionDisplay(values).map((value) => (
            <Typography key={value} component="span" variant="caption" color={value === "无" ? "text.secondary" : "text.primary"}>
              {value}
            </Typography>
          ))}
        </Stack>
      </Button>
    </TableCell>
  );
}
