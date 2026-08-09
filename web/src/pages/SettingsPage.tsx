import { useCallback, useEffect, useLayoutEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import StatePanel from "../components/common/StatePanel";
import SettingsPageContent from "../components/settings/SettingsPageContent";
import { useAppChrome } from "../contexts/AppChromeContext";
import { useAppHealthStatus, useCanMutateWithHealth } from "../contexts/AppHealthStatusContext";
import { useOptionalPageActivation } from "../contexts/PageRuntimeContext";
import { useSession, useSessionPermissions } from "../contexts/SessionContext";
import { importWorkflowPath } from "../features/imports/importRoutes";
import {
  createWorkbenchSettingsProject,
  deleteOaApplicantCredential,
  deleteWorkbenchSettingsProject,
  fetchActiveWorkbenchSettingsDataResetJob,
  fetchWorkbenchSettingsDataResetPreview,
  fetchWorkbenchAccessControl,
  fetchOaApplicantCredentials,
  fetchWorkbenchSettingsWithProgress,
  resetWorkbenchSettingsData,
  resumeWorkbenchSettingsDataResetJob,
  saveWorkbenchSettings,
  saveWorkbenchAccessControl,
  saveOaApplicantCredential,
  syncWorkbenchSettingsProjects,
  type WorkbenchBootstrapProgress,
  WorkbenchApiError,
} from "../features/workbench/api";
import type {
  OaApplicantCredentialSummary,
  SaveOaApplicantCredentialRequest,
  WorkbenchAccessAccount,
  WorkbenchAccessControl,
  WorkbenchSettings,
  WorkbenchSettingsDataResetAction,
  WorkbenchSettingsDataResetJob,
  WorkbenchSettingsDataResetPreview,
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
  const { active, activationGeneration } = useOptionalPageActivation("settings");
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
  const [oaApplicantCredentials, setOaApplicantCredentials] = useState<OaApplicantCredentialSummary[]>([]);
  const [isOaApplicantCredentialLoading, setIsOaApplicantCredentialLoading] = useState(false);
  const [isOaApplicantCredentialSaving, setIsOaApplicantCredentialSaving] = useState(false);
  const [accessControl, setAccessControl] = useState<WorkbenchAccessControl | null>(null);
  const [isAccessControlLoading, setIsAccessControlLoading] = useState(false);
  const [isAccessControlSaving, setIsAccessControlSaving] = useState(false);
  const [accessControlStatus, setAccessControlStatus] = useState<{
    tone: "success" | "error";
    message: string;
  } | null>(null);

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
    if (!active) {
      return undefined;
    }
    const controller = new AbortController();
    void loadSettings(controller.signal);
    return () => {
      controller.abort();
    };
  }, [active, activationGeneration, loadSettings]);

  useEffect(() => {
    if (!active || !canAdminAccess) {
      setAccessControl(null);
      setAccessControlStatus(null);
      setIsAccessControlLoading(false);
      return undefined;
    }
    const controller = new AbortController();
    setIsAccessControlLoading(true);
    setAccessControlStatus(null);
    fetchWorkbenchAccessControl(controller.signal)
      .then((payload) => {
        if (!controller.signal.aborted) {
          setAccessControl(payload);
        }
      })
      .catch((error) => {
        if (!controller.signal.aborted) {
          setAccessControlStatus({
            tone: "error",
            message: normalizeSettingsError(error, "访问账户加载失败，请稍后重试。"),
          });
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setIsAccessControlLoading(false);
        }
      });
    return () => controller.abort();
  }, [active, activationGeneration, canAdminAccess]);

  useEffect(() => {
    if (!active || !canAdminAccess) {
      setOaApplicantCredentials([]);
      setIsOaApplicantCredentialLoading(false);
      return;
    }
    const controller = new AbortController();
    setIsOaApplicantCredentialLoading(true);
    fetchOaApplicantCredentials(controller.signal)
      .then((credentials) => {
        if (!controller.signal.aborted) {
          setOaApplicantCredentials(credentials);
        }
      })
      .catch((error) => {
        if (!controller.signal.aborted) {
          setPageFeedback({
            tone: "error",
            message: normalizeSettingsError(error, "OA 申请人凭据加载失败，请稍后重试。"),
          });
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setIsOaApplicantCredentialLoading(false);
        }
      });
    return () => {
      controller.abort();
    };
  }, [active, activationGeneration, canAdminAccess]);

  useEffect(() => {
    if (!active || !canAdminAccess) {
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
  }, [active, activationGeneration, canAdminAccess, loadSettings]);

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

  const handleSaveAccessControl = async (accounts: WorkbenchAccessAccount[]): Promise<void> => {
    if (!canAdminAccess || accessControl === null) {
      setAccessControlStatus({ tone: "error", message: "当前账号没有管理员权限，不能维护访问账户。" });
      return;
    }
    if (healthStatus.blocksMutations) {
      setAccessControlStatus({ tone: "error", message: "登录已失效或系统不可用，不能维护访问账户。" });
      return;
    }
    setIsAccessControlSaving(true);
    setAccessControlStatus(null);
    try {
      const saved = await saveWorkbenchAccessControl({ version: accessControl.version, accounts });
      setAccessControl(saved);
      setAccessControlStatus({ tone: "success", message: "已保存访问账户。" });
    } catch (error) {
      const conflictVersion = error instanceof WorkbenchApiError && error.status === 409
        ? error.currentVersion
        : null;
      setAccessControlStatus({
        tone: "error",
        message: conflictVersion === null
          ? normalizeSettingsError(error, "访问账户保存失败，请稍后重试。")
          : "访问账户已被其他管理员更新，请保留当前编辑并刷新后重试。",
      });
    } finally {
      setIsAccessControlSaving(false);
    }
  };

  const handleSettingsDataReset = async (payload: {
    action: WorkbenchSettingsDataResetAction;
    oaPassword: string;
    idempotencyKey: string;
    reason: string;
    impactFingerprint: string;
    recoveryReceiptId: string;
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

  const handleLoadSettingsDataResetPreview = (
    action: WorkbenchSettingsDataResetAction,
  ): Promise<WorkbenchSettingsDataResetPreview> => fetchWorkbenchSettingsDataResetPreview(action);

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

  function mergeOaApplicantCredential(credential: OaApplicantCredentialSummary) {
    setOaApplicantCredentials((current) => {
      const filtered = current.filter((item) => item.targetApplicantCode !== credential.targetApplicantCode);
      return [...filtered, credential].sort((left, right) =>
        (left.targetApplicantName || left.targetApplicantCode).localeCompare(
          right.targetApplicantName || right.targetApplicantCode,
          "zh-CN",
        ),
      );
    });
  }

  const handleSaveOaApplicantCredential = async (
    payload: SaveOaApplicantCredentialRequest,
  ): Promise<void> => {
    if (!canAdminAccess) {
      throw new Error("当前账号没有管理员权限，不能维护 OA 申请人凭据。");
    }
    if (healthStatus.blocksMutations) {
      throw new Error("登录已失效或系统不可用，不能维护 OA 申请人凭据。");
    }
    setIsOaApplicantCredentialSaving(true);
    try {
      const saved = await saveOaApplicantCredential(payload);
      mergeOaApplicantCredential(saved);
    } finally {
      setIsOaApplicantCredentialSaving(false);
    }
  };

  const handleDeleteOaApplicantCredential = async (targetApplicantCode: string): Promise<void> => {
    if (!canAdminAccess) {
      throw new Error("当前账号没有管理员权限，不能维护 OA 申请人凭据。");
    }
    if (healthStatus.blocksMutations) {
      throw new Error("登录已失效或系统不可用，不能维护 OA 申请人凭据。");
    }
    setIsOaApplicantCredentialSaving(true);
    try {
      const saved = await deleteOaApplicantCredential(targetApplicantCode);
      mergeOaApplicantCredential(saved);
    } finally {
      setIsOaApplicantCredentialSaving(false);
    }
  };

  const handleStayOnSettings = useCallback(() => {
    navigate("/settings");
  }, [navigate]);

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
    <div className="settings-route" data-testid="settings-page">
      <div className="settings-route-status">
        {pageFeedback ? (
          <StatePanel compact tone={pageFeedback.tone}>
            {pageFeedback.message}
          </StatePanel>
        ) : null}
        {loadError ? <StatePanel compact tone="error">{loadError}</StatePanel> : null}
        {isLoading && !loadError ? (
          <StatePanel compact tone="loading">
            {loadProgress.percent === null
              ? "正在同步关联台设置..."
              : `${loadProgress.label} ${loadProgress.percent}%`}
          </StatePanel>
        ) : null}
      </div>
      {!isLoading && !loadError && settings ? (
        <SettingsPageContent
          canManageAccessControl={canAdminAccess}
          accessControl={accessControl}
          accessControlStatus={accessControlStatus}
          canSave={canMutateData && canMutateWithHealth}
          isSaving={isSaving}
          isAccessControlLoading={isAccessControlLoading}
          isAccessControlSaving={isAccessControlSaving}
          isOaApplicantCredentialLoading={isOaApplicantCredentialLoading}
          isOaApplicantCredentialSaving={isOaApplicantCredentialSaving}
          oaApplicantCredentials={oaApplicantCredentials}
          settings={settings}
          activeDataResetJob={activeDataResetJob}
          onCreateProject={handleCreateSettingsProject}
          onDataReset={handleSettingsDataReset}
          onLoadDataResetPreview={handleLoadSettingsDataResetPreview}
          onDeleteProject={handleDeleteSettingsProject}
          onDeleteOaApplicantCredential={handleDeleteOaApplicantCredential}
          onSave={handleSaveSettings}
          onSaveAccessControl={handleSaveAccessControl}
          onSaveOaApplicantCredential={handleSaveOaApplicantCredential}
          onSyncProjects={handleSyncSettingsProjects}
        />
      ) : null}
    </div>
  );
}
