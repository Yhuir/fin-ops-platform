import { Accordion, Button, Checkbox } from "@heroui/react";
import { useEffect, useRef, useState } from "react";
import AppDrawer from "../common/AppDrawer";
import { exportTaxCertifications } from "../../features/tax/api";
import type { TaxCertificationFilters, TaxExportField } from "../../features/tax/types";

export default function TaxCertificationExportDrawer({ filters, fields, onClose }: {
  filters: TaxCertificationFilters; fields: TaxExportField[]; onClose: () => void;
}) {
  const [selected, setSelected] = useState(() => fields.filter(field => field.default_selected).map(field => field.key));
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [completed, setCompleted] = useState(false);
  const contentRef = useRef<HTMLDivElement>(null);
  const wasPending = useRef(false);
  useEffect(() => { if (wasPending.current && !pending) contentRef.current?.focus(); wasPending.current = pending; }, [pending]);
  function renderFields(items: TaxExportField[]) {
    return <div className="tax-export-fields">{items.map(field => <Checkbox key={field.key} isSelected={selected.includes(field.key)} isDisabled={pending}
      onChange={checked => { setCompleted(false); setSelected(current => checked ? [...current, field.key] : current.filter(key => key !== field.key)); }}>
      <Checkbox.Control><Checkbox.Indicator /></Checkbox.Control><Checkbox.Content>{field.label}</Checkbox.Content>
    </Checkbox>)}</div>;
  }
  async function download() {
    setPending(true); setError(""); setCompleted(false);
    try {
      const { blob, fileName } = await exportTaxCertifications(filters, fields.filter(field => selected.includes(field.key)).map(field => field.key));
      const url = URL.createObjectURL(blob); const link = document.createElement("a");
      link.href = url; link.download = fileName; document.body.appendChild(link); link.click(); link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000); setCompleted(true);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "导出失败"); }
    finally { setPending(false); }
  }
  return <AppDrawer open isDismissable title="导出专票清单" onClose={onClose} closeDisabled={pending} width="min(480px, 100vw)"
    footer={<div className="tax-import-actions"><Button variant="secondary" isDisabled={pending} onPress={onClose}>取消</Button><Button variant="primary" onPress={download} isPending={pending} isDisabled={pending || !selected.length}>导出专票清单</Button></div>}>
    <div ref={contentRef} tabIndex={-1} className="tax-certification-drawer-content">
      <div className="tax-export-heading"><h3>导出字段</h3><span>{selected.length}/{fields.length}</span><Button size="sm" variant="ghost" isDisabled={pending} onPress={() => { setSelected(fields.filter(field => field.default_selected).map(field => field.key)); setCompleted(false); }}>恢复默认</Button></div>{renderFields(fields.filter(field => field.default_selected))}
      <Accordion><Accordion.Item id="other-fields"><Accordion.Heading><Accordion.Trigger>更多字段<Accordion.Indicator /></Accordion.Trigger></Accordion.Heading>
        <Accordion.Panel>{renderFields(fields.filter(field => !field.default_selected))}</Accordion.Panel></Accordion.Item></Accordion>
      {error ? <div role="alert">{error}</div> : null}{completed ? <div role="status">已导出</div> : null}
    </div>
  </AppDrawer>;
}
