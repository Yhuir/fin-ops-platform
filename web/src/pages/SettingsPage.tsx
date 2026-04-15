import { useCallback, useEffect, useLayoutEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import WorkbenchSettingsModal from "../components/workbench/WorkbenchSettingsModal";
import { type WorkbenchHeaderIntent, useAppChrome } from "../contexts/AppChromeContext";
import { useSession, useSessionPermissions } from "../contexts/SessionContext";
import {
  createWorkbenchSettingsProject,
  deleteWorkbenchSettingsProject,
  fetchWorkbenchSettingsWithProgress,
  resetWorkbenchSettingsData,
  saveWorkbenchSettings,
  syncWorkbenchSettingsProjects,
  type WorkbenchBootstrapProgress,
} from "../features/workbench/api";
import type {
  WorkbenchSettings,
  WorkbenchSettingsDataResetAction,
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
  const { setWorkbenchHeaderActions, setWorkbenchStatusText } = useAppChrome();
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
    if (isLoading) {
      setWorkbenchStatusText(
        loadProgress.percent === null
          ? `${loadProgress.label}...`
          : `${loadProgress.label} ${loadProgress.percent}%`,
      );
      return;
    }
    setWorkbenchStatusText(null);
  }, [isLoading, loadProgress.label, loadProgress.percent, setWorkbenchStatusText]);

  useEffect(() => () => setWorkbenchStatusText(null), [setWorkbenchStatusText]);

  const handleSaveSettings = async (payload: {
    completedProjectIds: string[];
    bankAccountMappings: WorkbenchSettings["bankAccountMappings"];
    allowedUsernames: string[];
    readonlyExportUsernames: string[];
    adminUsernames: string[];
    workbenchColumnLayouts: WorkbenchSettings["workbenchColumnLayouts"];
    oaRetention: WorkbenchSettings["oaRetention"];
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
  }): Promise<WorkbenchSettingsDataResetResult> => {
    if (!canAdminAccess) {
      throw new Error("当前账号没有管理员权限，不能执行数据重置。");
    }
    const result = await resetWorkbenchSettingsData(payload);
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
        <div className={`state-panel${pageFeedback.tone === "error" ? " error" : ""}`}>{pageFeedback.message}</div>
      ) : null}
      {loadError ? <div className="state-panel error">{loadError}</div> : null}
      {isLoading && !loadError ? <div className="state-panel">正在同步关联台设置...</div> : null}
      {!isLoading && !loadError && settings ? (
        <WorkbenchSettingsModal
          canManageAccessControl={canAdminAccess}
          canSave={canMutateData}
          isSaving={isSaving}
          settings={settings}
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
