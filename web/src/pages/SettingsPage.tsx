import { Button } from "@heroui/react";
import { X } from "lucide-react";
import { useCallback, useEffect, useLayoutEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import StatePanel from "../components/common/StatePanel";
import BatchAccountingHistory from "../components/batchAccounting/BatchAccountingHistory";
import SettingsTabs from "../components/settings/SettingsTabs";
import { settingsNavigation } from "../components/settings/navigation";
import type { SettingsSectionId } from "../components/settings/types";
import SettingsPageContent from "../components/settings/SettingsPageContent";
import { useAppChrome } from "../contexts/AppChromeContext";
import { useAppHealthStatus, useCanMutateWithHealth } from "../contexts/AppHealthStatusContext";
import { useOptionalPageActivation } from "../contexts/PageRuntimeContext";
import { useSessionPermissions } from "../contexts/SessionContext";
import { importWorkflowPath } from "../features/imports/importRoutes";
import {
  fetchActiveWorkbenchSettingsDataResetJob,
  fetchWorkbenchSettingsDataResetPreview,
  fetchWorkbenchAccessControl,
  fetchWorkbenchSettingsWithProgress,
  resetWorkbenchSettingsData,
  resumeWorkbenchSettingsDataResetJob,
  saveWorkbenchSettings,
  saveWorkbenchAccessControl,
  searchWorkbenchAccessUsers,
  type WorkbenchBootstrapProgress,
  WorkbenchApiError,
} from "../features/workbench/api";
import type {
  WorkbenchAccessAccount,
  WorkbenchAccessControl,
  WorkbenchSettings,
  WorkbenchSettingsDataResetAction,
  WorkbenchSettingsDataResetJob,
  WorkbenchSettingsDataResetPreview,
  WorkbenchSettingsDataResetResult,
} from "../features/workbench/types";

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
  const { canAccessPage } = useSessionPermissions();
  const [searchParams] = useSearchParams();
  if (searchParams.get("section") === "batch-accounting" && !canAccessPage("batch-accounting")) return <StatePanel tone="error">没有批量账务查看权限</StatePanel>;
  if (canAccessPage("settings")) return <EditableSettingsPage />;
  if (!canAccessPage("batch-accounting")) return <StatePanel tone="error">没有设置访问权限</StatePanel>;
  return <div className="settings-route" data-testid="settings-page"><HistorySettingsWorkspace canViewSettings={false} canAdminAccess={false} /></div>;
}

function HistorySettingsWorkspace({ canViewSettings, canAdminAccess }: { canViewSettings: boolean; canAdminAccess: boolean }) {
  const [, setSearchParams] = useSearchParams();
  const items = settingsNavigation(canViewSettings, canAdminAccess, true);
  return <div className="settings-layout"><div className="settings-workspace">
    <header className="settings-content-header"><div className="settings-content-title"><h1>设置</h1></div><div className="settings-save-actions" /></header>
    <SettingsTabs items={items} activeSectionId="batch-accounting" onSelect={(section: SettingsSectionId) => setSearchParams({ section }, { replace: true })}>
      <BatchAccountingHistory />
    </SettingsTabs>
  </div></div>;
}

function EditableSettingsPage() {
  const { active, activationGeneration } = useOptionalPageActivation("settings");
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const showingHistory = searchParams.get("section") === "batch-accounting";
  const healthStatus = useAppHealthStatus();
  const canMutateWithHealth = useCanMutateWithHealth();
  const { canAdminAccess, canAccessPage } = useSessionPermissions();
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
  const [accessControl, setAccessControl] = useState<WorkbenchAccessControl | null>(null);
  const [isAccessControlLoading, setIsAccessControlLoading] = useState(false);
  const [isAccessControlSaving, setIsAccessControlSaving] = useState(false);

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
    if (!active || showingHistory || settings !== null) {
      return undefined;
    }
    const controller = new AbortController();
    void loadSettings(controller.signal);
    return () => {
      controller.abort();
    };
  }, [active, activationGeneration, showingHistory, settings, loadSettings]);

  useEffect(() => {
    if (showingHistory) return;
    if (!active || !canAdminAccess) {
      setAccessControl(null);
      setIsAccessControlLoading(false);
      return undefined;
    }
    if (accessControl !== null) return;
    const controller = new AbortController();
    setIsAccessControlLoading(true);
    setPageFeedback(null);
    fetchWorkbenchAccessControl(controller.signal)
      .then((payload) => {
        if (!controller.signal.aborted) {
          setAccessControl(payload);
        }
      })
      .catch((error) => {
        if (!controller.signal.aborted) {
          setPageFeedback({
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
  }, [active, activationGeneration, canAdminAccess, showingHistory, accessControl]);

  useEffect(() => {
    if (showingHistory) return;
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
  }, [active, activationGeneration, canAdminAccess, showingHistory, loadSettings]);

  useEffect(() => {
    if (showingHistory) { setWorkbenchStatus(null); return; }
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
  }, [showingHistory, isLoading, loadError, loadProgress.label, loadProgress.percent, setWorkbenchStatus]);

  useEffect(() => () => setWorkbenchStatus(null), [setWorkbenchStatus]);

  const handleSaveSettings = async (payload: {
    bankAccountMappings: WorkbenchSettings["bankAccountMappings"];
    workbenchColumnLayouts: WorkbenchSettings["workbenchColumnLayouts"];
    oaRetention: WorkbenchSettings["oaRetention"];
    oaImport: WorkbenchSettings["oaImport"];
  }): Promise<WorkbenchSettings | null> => {
    if (healthStatus.blocksMutations) {
      setPageFeedback({ tone: "error", message: "登录已失效或系统不可用，不能保存设置。" });
      return null;
    }
    setIsSaving(true);
    setPageFeedback(null);
    try {
      const saved = await saveWorkbenchSettings(payload);
      setSettings(saved);
      setPageFeedback({ tone: "success", message: "已保存银行账户与 OA 导入设置。" });
      return saved;
    } catch (error) {
      setPageFeedback({ tone: "error", message: `保存设置失败：${normalizeSettingsError(error, "请稍后重试。")}` });
      return null;
    } finally {
      setIsSaving(false);
    }
  };

  const handleSaveAccessControl = async (accounts: WorkbenchAccessAccount[]): Promise<void> => {
    if (!canAdminAccess || accessControl === null) {
      setPageFeedback({ tone: "error", message: "当前账号没有管理员权限，不能维护访问账户。" });
      return;
    }
    if (healthStatus.blocksMutations) {
      setPageFeedback({ tone: "error", message: "登录已失效或系统不可用，不能维护访问账户。" });
      return;
    }
    setIsAccessControlSaving(true);
    setPageFeedback(null);
    try {
      const saved = await saveWorkbenchAccessControl({ version: accessControl.version, accounts });
      setAccessControl(saved);
      setPageFeedback({ tone: "success", message: "已保存访问账户。" });
    } catch (error) {
      const conflictVersion = error instanceof WorkbenchApiError && error.status === 409
        ? error.currentVersion
        : null;
      setPageFeedback({
        tone: "error",
        message: conflictVersion === null
          ? `${normalizeSettingsError(error, "访问账户保存失败，请稍后重试。")}${error instanceof WorkbenchApiError && error.requestId ? `（请求编号：${error.requestId}）` : ""}`
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


  const handleStayOnSettings = useCallback(() => {
    navigate("/settings");
  }, [navigate]);

  useLayoutEffect(() => {
    setWorkbenchHeaderActions({
      canOperateData: canMutateWithHealth,
      onOpenImport: (mode) => navigate(importWorkflowPath(mode)),
      onOpenSettings: handleStayOnSettings,
    });
    return () => {
      setWorkbenchHeaderActions(null);
    };
  }, [canMutateWithHealth, handleStayOnSettings, navigate, setWorkbenchHeaderActions]);

  return (
    <div className="settings-route" data-testid="settings-page">
      {pageFeedback ? (
        <div className="settings-save-feedback">
          <StatePanel compact tone={pageFeedback.tone}>{pageFeedback.message}</StatePanel>
          <Button aria-label="关闭设置反馈" isIconOnly size="sm" variant="ghost" onPress={() => setPageFeedback(null)}><X size={16} aria-hidden="true" /></Button>
        </div>
      ) : null}
      {showingHistory && settings === null ? <HistorySettingsWorkspace canViewSettings canAdminAccess={canAdminAccess} /> : null}
      <div className="settings-route-status" hidden={showingHistory}>
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
          canViewBatchHistory={canAccessPage("batch-accounting")}
          canManageAccessControl={canAdminAccess}
          accessControl={accessControl}
          onFeedback={setPageFeedback}
          canSave={canMutateWithHealth}
          isSaving={isSaving}
          isAccessControlLoading={isAccessControlLoading}
          isAccessControlSaving={isAccessControlSaving}
          settings={settings}
          activeDataResetJob={activeDataResetJob}
          onDataReset={handleSettingsDataReset}
          onLoadDataResetPreview={handleLoadSettingsDataResetPreview}
          onSave={handleSaveSettings}
          onSaveAccessControl={handleSaveAccessControl}
          onSearchAccessUsers={searchWorkbenchAccessUsers}
        />
      ) : null}
    </div>
  );
}
