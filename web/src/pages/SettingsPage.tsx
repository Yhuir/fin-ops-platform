import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";

import SettingsPageContent from "../components/settings/SettingsPageContent";
import { useAppChrome } from "../contexts/AppChromeContext";
import { useAppHealthStatus, useCanMutateWithHealth } from "../contexts/AppHealthStatusContext";
import { useSession, useSessionPermissions } from "../contexts/SessionContext";
import { importWorkflowPath } from "../features/imports/importRoutes";
import {
  createWorkbenchSettingsProject,
  deleteWorkbenchSettingsProject,
  fetchActiveWorkbenchSettingsDataResetJob,
  fetchWorkbenchSettingsWithProgress,
  resetWorkbenchSettingsData,
  resumeWorkbenchSettingsDataResetJob,
  saveWorkbenchSettings,
  syncWorkbenchSettingsProjects,
  type WorkbenchBootstrapProgress,
} from "../features/workbench/api";
import type {
  WorkbenchSettings,
  WorkbenchSettingsDataResetAction,
  WorkbenchSettingsDataResetJob,
  WorkbenchSettingsDataResetResult,
} from "../features/workbench/types";

const READONLY_ACTION_MESSAGE = "当前账号仅支持查看和导出，不能保存设置。";
const TAG_SYNC_EVENT = "finops:bank-transaction-tags-updated";
const TAG_VERSION_STORAGE_KEY = "finops.bankTransactionTags.version";

function broadcastBankTransactionTagsUpdated(version: number) {
  try {
    window.localStorage.setItem(TAG_VERSION_STORAGE_KEY, String(version));
  } catch {
    // localStorage can be unavailable in embedded shells.
  }
  window.dispatchEvent(new CustomEvent(TAG_SYNC_EVENT, { detail: { version } }));
  if (typeof BroadcastChannel !== "undefined") {
    const channel = new BroadcastChannel(TAG_SYNC_EVENT);
    channel.postMessage({ version });
    channel.close();
  }
}

function tagVersionFromEvent(event: Event) {
  if (!(event instanceof CustomEvent) || !event.detail || typeof event.detail !== "object") {
    return null;
  }
  const version = Number((event.detail as { version?: unknown }).version);
  return Number.isFinite(version) && version > 0 ? version : null;
}

function readPersistedTagVersion() {
  try {
    const version = Number(window.localStorage.getItem(TAG_VERSION_STORAGE_KEY));
    return Number.isFinite(version) && version > 0 ? version : null;
  } catch {
    return null;
  }
}

function settingsActorId(session: ReturnType<typeof useSession>) {
  return session.status === "authenticated" || session.status === "forbidden"
    ? session.session.user.username
    : "web_finance_user";
}

function normalizeSettingsError(error: unknown, fallback: string) {
  if (error instanceof Error && error.message.trim()) {
    try {
      const payload = JSON.parse(error.message) as { message?: unknown };
      if (typeof payload.message === "string" && payload.message.trim()) {
        return payload.message;
      }
    } catch {
      return error.message;
    }
    return error.message;
  }
  return fallback;
}

export default function SettingsPage() {
  const navigate = useNavigate();
  const session = useSession();
  const healthStatus = useAppHealthStatus();
  const canMutateWithHealth = useCanMutateWithHealth();
  const { canMutateData, canAdminAccess } = useSessionPermissions();
  const { setWorkbenchHeaderActions, setWorkbenchStatus } = useAppChrome();
  const [settings, setSettings] = useState<WorkbenchSettings | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loadProgress, setLoadProgress] = useState<WorkbenchBootstrapProgress>({
    label: "正在同步关联台设置",
    loadedBytes: 0,
    totalBytes: 0,
    percent: null,
    indeterminate: true,
  });
  const [pageFeedback, setPageFeedback] = useState<{ tone: "success" | "error"; message: string } | null>(null);
  const [activeDataResetJob, setActiveDataResetJob] = useState<WorkbenchSettingsDataResetJob | null>(null);
  const [staleBankTransactionTagsVersion, setStaleBankTransactionTagsVersion] = useState<number | null>(null);
  const localTagBroadcastVersionRef = useRef<number | null>(null);

  const loadSettings = useCallback(async (signal?: AbortSignal) => {
    setIsLoading(true);
    setLoadError(null);
    try {
      const payload = await fetchWorkbenchSettingsWithProgress(signal, (progress) => {
        setLoadProgress(progress);
      });
      if (signal?.aborted) {
        return;
      }
      setSettings(payload);
      setStaleBankTransactionTagsVersion(null);
    } catch (error) {
      if (signal?.aborted) {
        return;
      }
      setLoadError(normalizeSettingsError(error, "设置加载失败，请稍后重试。"));
    } finally {
      if (!signal?.aborted) {
        setIsLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void loadSettings(controller.signal);
    return () => {
      controller.abort();
    };
  }, [loadSettings]);

  useEffect(() => {
    if (!canAdminAccess) {
      setActiveDataResetJob(null);
      return;
    }
    let cancelled = false;

    async function restoreActiveDataResetJob() {
      try {
        const job = await fetchActiveWorkbenchSettingsDataResetJob();
        if (cancelled || job === null || ["completed", "failed", "error", "cancelled", "canceled"].includes(job.status)) {
          return;
        }
        setActiveDataResetJob(job);
        const result = await resumeWorkbenchSettingsDataResetJob(job, {
          onProgress: (nextJob) => {
            if (!cancelled) {
              setActiveDataResetJob(nextJob);
            }
          },
        });
        if (cancelled) {
          return;
        }
        setActiveDataResetJob(null);
        await loadSettings();
        setPageFeedback({ tone: "success", message: result.message });
      } catch (error) {
        if (!cancelled) {
          setActiveDataResetJob(null);
          setPageFeedback({ tone: "error", message: normalizeSettingsError(error, "数据重置状态恢复失败，请稍后重试。") });
        }
      }
    }

    void restoreActiveDataResetJob();
    return () => {
      cancelled = true;
    };
  }, [canAdminAccess, loadSettings]);

  useEffect(() => {
    const currentVersion = settings?.bankTransactionTags.version ?? null;
    const markStaleIfNewer = (version: number | null) => {
      if (version === null || currentVersion === null || version <= currentVersion) {
        return;
      }
      if (localTagBroadcastVersionRef.current === version) {
        return;
      }
      setStaleBankTransactionTagsVersion(version);
      setPageFeedback({
        tone: "error",
        message: "银行明细标签已在其他页面更新，请刷新后再保存。",
      });
    };

    const handleTagUpdate = (event: Event) => {
      markStaleIfNewer(tagVersionFromEvent(event));
    };
    const handleStorage = (event: StorageEvent) => {
      if (event.key !== TAG_VERSION_STORAGE_KEY) {
        return;
      }
      const version = Number(event.newValue);
      markStaleIfNewer(Number.isFinite(version) && version > 0 ? version : null);
    };
    const handleFocus = () => {
      markStaleIfNewer(readPersistedTagVersion());
    };

    window.addEventListener(TAG_SYNC_EVENT, handleTagUpdate);
    window.addEventListener("storage", handleStorage);
    window.addEventListener("focus", handleFocus);

    let channel: BroadcastChannel | null = null;
    if (typeof BroadcastChannel !== "undefined") {
      channel = new BroadcastChannel(TAG_SYNC_EVENT);
      channel.onmessage = (message) => {
        const version = Number((message.data as { version?: unknown } | undefined)?.version);
        window.dispatchEvent(new CustomEvent(TAG_SYNC_EVENT, { detail: { version: Number.isFinite(version) ? version : undefined } }));
      };
    }

    return () => {
      window.removeEventListener(TAG_SYNC_EVENT, handleTagUpdate);
      window.removeEventListener("storage", handleStorage);
      window.removeEventListener("focus", handleFocus);
      channel?.close();
    };
  }, [settings?.bankTransactionTags.version]);

  useEffect(() => {
    if (loadError) {
      setWorkbenchStatus({ level: "error", reason: loadError });
      return;
    }
    if (isLoading) {
      const reason = loadProgress.percent === null
        ? `${loadProgress.label}...`
        : `${loadProgress.label} ${loadProgress.percent}%`;
      setWorkbenchStatus({ level: "pending", reason });
      return;
    }
    setWorkbenchStatus(null);
  }, [isLoading, loadError, loadProgress.label, loadProgress.percent, setWorkbenchStatus]);

  useEffect(() => () => setWorkbenchStatus(null), [setWorkbenchStatus]);

  const handleSaveSettings = async (payload: {
    completedProjectIds: string[];
    bankAccountMappings: WorkbenchSettings["bankAccountMappings"];
    allowedUsernames: string[];
    readonlyExportUsernames: string[];
    adminUsernames: string[];
    workbenchColumnLayouts: WorkbenchSettings["workbenchColumnLayouts"];
    oaRetention: WorkbenchSettings["oaRetention"];
    oaImport: WorkbenchSettings["oaImport"];
    oaInvoiceOffset: WorkbenchSettings["oaInvoiceOffset"];
    bankTransactionTags: WorkbenchSettings["bankTransactionTags"];
    pendingInvoiceTagGroups: WorkbenchSettings["pendingInvoiceTagGroups"];
  }) => {
    if (!canMutateData) {
      setPageFeedback({ tone: "error", message: READONLY_ACTION_MESSAGE });
      return;
    }
    if (healthStatus.blocksMutations) {
      setPageFeedback({ tone: "error", message: "登录已失效或系统不可用，不能保存设置。" });
      return;
    }
    if (
      staleBankTransactionTagsVersion !== null
      && staleBankTransactionTagsVersion > payload.bankTransactionTags.version
    ) {
      setPageFeedback({
        tone: "error",
        message: "银行明细标签已在其他页面更新，请刷新后再保存。",
      });
      return;
    }
    setIsSaving(true);
    setPageFeedback(null);
    try {
      const saved = await saveWorkbenchSettings(payload);
      localTagBroadcastVersionRef.current = saved.bankTransactionTags.version;
      setSettings(saved);
      setStaleBankTransactionTagsVersion(null);
      broadcastBankTransactionTagsUpdated(saved.bankTransactionTags.version);
      setPageFeedback({ tone: "success", message: "已保存关联台设置。" });
    } catch (error) {
      setPageFeedback({ tone: "error", message: normalizeSettingsError(error, "保存设置失败，请稍后重试。") });
    } finally {
      setIsSaving(false);
    }
  };

  const handleSettingsDataReset = async (payload: {
    action: WorkbenchSettingsDataResetAction;
    oaPassword: string;
    onProgress?: (job: WorkbenchSettingsDataResetJob) => void;
  }): Promise<WorkbenchSettingsDataResetResult> => {
    if (!canAdminAccess) {
      throw new Error("当前账号没有管理员权限，不能执行数据重置。");
    }
    if (healthStatus.blocksMutations) {
      throw new Error("登录已失效或系统不可用，不能执行数据清理。");
    }
    const result = await resetWorkbenchSettingsData({
      ...payload,
      onProgress: (job) => {
        setActiveDataResetJob(job);
        payload.onProgress?.(job);
      },
    });
    setActiveDataResetJob(null);
    await loadSettings();
    setPageFeedback({ tone: "success", message: result.message });
    return result;
  };

  const handleSyncSettingsProjects = async (): Promise<WorkbenchSettings> => {
    if (!canMutateData) {
      throw new Error(READONLY_ACTION_MESSAGE);
    }
    if (healthStatus.blocksMutations) {
      throw new Error("登录已失效或系统不可用，不能保存设置。");
    }
    const saved = await syncWorkbenchSettingsProjects(settingsActorId(session));
    setSettings(saved);
    setPageFeedback({ tone: "success", message: "已从 OA 拉取项目。" });
    return saved;
  };

  const handleCreateSettingsProject = async (payload: {
    projectCode: string;
    projectName: string;
  }): Promise<WorkbenchSettings> => {
    if (!canMutateData) {
      throw new Error(READONLY_ACTION_MESSAGE);
    }
    if (healthStatus.blocksMutations) {
      throw new Error("登录已失效或系统不可用，不能保存设置。");
    }
    const saved = await createWorkbenchSettingsProject({
      actorId: settingsActorId(session),
      projectCode: payload.projectCode,
      projectName: payload.projectName,
    });
    setSettings(saved);
    setPageFeedback({ tone: "success", message: "已新增本地项目。" });
    return saved;
  };

  const handleDeleteSettingsProject = async (projectId: string): Promise<WorkbenchSettings> => {
    if (!canMutateData) {
      throw new Error(READONLY_ACTION_MESSAGE);
    }
    if (healthStatus.blocksMutations) {
      throw new Error("登录已失效或系统不可用，不能保存设置。");
    }
    const saved = await deleteWorkbenchSettingsProject(projectId);
    setSettings(saved);
    setPageFeedback({ tone: "success", message: "已删除本地项目或状态覆盖。" });
    return saved;
  };

  const handleStayOnSettings = useCallback(() => {
    navigate("/settings");
  }, [navigate]);

  const handleRefreshSettings = useCallback(() => {
    setPageFeedback(null);
    void loadSettings();
  }, [loadSettings]);

  useLayoutEffect(() => {
    setWorkbenchHeaderActions({
      canMutateData: canMutateData && canMutateWithHealth,
      onOpenImport: (mode) => navigate(importWorkflowPath(mode)),
      onOpenSettings: handleStayOnSettings,
    });
    return () => {
      setWorkbenchHeaderActions(null);
    };
  }, [canMutateData, canMutateWithHealth, handleStayOnSettings, navigate, setWorkbenchHeaderActions]);

  return (
    <Box data-testid="settings-page" sx={{ display: "flex", flexDirection: "column", flex: 1, height: "100%" }}>
      <Stack spacing={2} sx={{ mb: 3 }}>
        {pageFeedback ? (
          <Alert
            action={staleBankTransactionTagsVersion !== null ? (
              <Button color="inherit" size="small" onClick={handleRefreshSettings}>
                刷新设置
              </Button>
            ) : null}
            severity={pageFeedback.tone === "error" ? "error" : "success"}
          >
            {pageFeedback.message}
          </Alert>
        ) : null}
        {loadError ? <Alert severity="error">{loadError}</Alert> : null}
        {isLoading && !loadError ? <Alert severity="info">正在同步关联台设置...</Alert> : null}
      </Stack>
      {!isLoading && !loadError && settings ? (
        <SettingsPageContent
          canManageAccessControl={canAdminAccess}
          canSave={canMutateData && canMutateWithHealth}
          isSaving={isSaving}
          settings={settings}
          activeDataResetJob={activeDataResetJob}
          onCreateProject={handleCreateSettingsProject}
          onDataReset={handleSettingsDataReset}
          onDeleteProject={handleDeleteSettingsProject}
          onSave={handleSaveSettings}
          onSyncProjects={handleSyncSettingsProjects}
        />
      ) : null}
    </Box>
  );
}
