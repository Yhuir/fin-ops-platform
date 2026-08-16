import AppDrawer from "../common/AppDrawer";
import EntityDetailContent, {
  preparePublicDetailSections,
  type EntityDetailField,
} from "../common/EntityDetailContent";
import type { WorkbenchRecord } from "../../features/workbench/types";

type DetailDrawerProps = {
  row: WorkbenchRecord | null;
  loading: boolean;
  error: string | null;
  onClose: () => void;
};

const drawerTitles: Record<WorkbenchRecord["recordType"], string> = {
  oa: "OA详情",
  bank: "银行流水详情",
  invoice: "发票详情",
};

const sectionTitles: Record<WorkbenchRecord["recordType"], string> = {
  oa: "基本信息",
  bank: "交易信息",
  invoice: "基本信息",
};

export default function DetailDrawer({ row, loading, error, onClose }: DetailDrawerProps) {
  const open = Boolean(row);
  const title = row ? drawerTitles[row.recordType] : "详情";
  const sections = row
    ? preparePublicDetailSections([{
        title: sectionTitles[row.recordType],
        fields: row.detailFields.map((field): EntityDetailField => ({
          label: field.label,
          value: sanitizeAttachmentValue(field.value),
        })),
      }])
    : [];

  return (
    <AppDrawer
      className="workbench-detail-drawer"
      closeLabel="关闭详情抽屉"
      open={open}
      title={title}
      width="min(800px, 100vw)"
      onClose={onClose}
    >
      <div className="workbench-detail-drawer__body">
        <EntityDetailContent error={error} loading={loading} sections={sections} />
      </div>
    </AppDrawer>
  );
}

function sanitizeAttachmentValue(value: string) {
  return value.replace(/\s*[（(][0-9a-f]{16,}\.(?:png|jpg|jpeg|pdf)[）)]/gi, "");
}
