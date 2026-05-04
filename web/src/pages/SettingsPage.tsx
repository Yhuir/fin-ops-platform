import { useCallback, useEffect, useLayoutEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import Alert from "@mui/material/Alert";

import SettingsPageContent from "../components/settings/SettingsPageContent";
import { type WorkbenchHeaderIntent, useAppChrome } from "../contexts/AppChromeContext";
import { useSession, useSessionPermissions } from "../contexts/SessionContext";
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
  }) => {
    if (!canMutateData) {
      setPageFeedback({ tone: "error", message: READONLY_ACTION_MESSAGE });
      return;
    }
    setIsSaving(true);
    setPageFeedback(null);
    try {
      const saved = await saveWorkbenchSettings(payload);
      setSettings(saved);
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
    const saved = await deleteWorkbenchSettingsProject(projectId);
    setSettings(saved);
    setPageFeedback({ tone: "success", message: "已删除本地项目或状态覆盖。" });
    return saved;
  };

  const handleRouteToWorkbenchIntent = useCallback((intent: WorkbenchHeaderIntent) => {
    navigate("/", {
      state: {
        workbenchHeaderIntent: intent,
      },
    });
  }, [navigate]);

  const handleStayOnSettings = useCallback(() => {
    navigate("/settings");
  }, [navigate]);

  useLayoutEffect(() => {
    setWorkbenchHeaderActions({
      canMutateData,
      onOpenImport: (mode) => handleRouteToWorkbenchIntent({ type: "open_import", mode }),
      onOpenSearch: () => handleRouteToWorkbenchIntent({ type: "open_search" }),
      onOpenSettings: handleStayOnSettings,
    });
    return () => {
      setWorkbenchHeaderActions(null);
    };
  }, [canMutateData, handleRouteToWorkbenchIntent, handleStayOnSettings, setWorkbenchHeaderActions]);

  return (
    <div className="page-stack settings-page-shell" data-testid="settings-page">
      {pageFeedback ? (
        <Alert severity={pageFeedback.tone === "error" ? "error" : "success"}>{pageFeedback.message}</Alert>
      ) : null}
      {loadError ? <Alert severity="error">{loadError}</Alert> : null}
      {isLoading && !loadError ? <Alert severity="info">正在同步关联台设置...</Alert> : null}
      {!isLoading && !loadError && settings ? (
        <SettingsPageContent
          canManageAccessControl={canAdminAccess}
          canSave={canMutateData}
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
    </div>
  );
}
