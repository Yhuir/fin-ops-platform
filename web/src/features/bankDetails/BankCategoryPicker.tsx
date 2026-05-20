import { useEffect, useId, useMemo, useRef, useState, type MouseEvent } from "react";
import ArrowDropDownIcon from "@mui/icons-material/ArrowDropDown";
import ButtonBase from "@mui/material/ButtonBase";
import ListSubheader from "@mui/material/ListSubheader";
import MenuItem from "@mui/material/MenuItem";
import MenuList from "@mui/material/MenuList";
import Popover from "@mui/material/Popover";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";

import BankCategoryTag from "./BankCategoryTag";
import type { BankTransactionCategoryCode } from "./types";
import type { BankTransactionTagDefinition } from "../pendingInvoices/types";

type BankCategoryPickerProps = {
  rowId: string;
  categoryCode: BankTransactionCategoryCode | null;
  categoryLabel: string | null;
  categorySource: string;
  categoryOptions: BankTransactionTagDefinition[];
  onChange: (categoryCode: BankTransactionCategoryCode | null) => void;
};

function getCategoryLabel(
  categoryCode: BankTransactionCategoryCode | null,
  categoryLabel: string | null,
  categoryOptions: BankTransactionTagDefinition[],
) {
  if (!categoryCode) {
    return "未分类";
  }
  return categoryLabel?.trim() || categoryOptions.find((option) => option.code === categoryCode)?.label || categoryCode;
}

export default function BankCategoryPicker({
  rowId,
  categoryCode,
  categoryLabel,
  categoryOptions,
  onChange,
}: BankCategoryPickerProps) {
  const menuId = useId();
  const [anchorEl, setAnchorEl] = useState<HTMLElement | null>(null);
  const selectedOptionRef = useRef<HTMLLIElement | null>(null);
  const open = Boolean(anchorEl);
  const displayLabel = getCategoryLabel(categoryCode, categoryLabel, categoryOptions);
  const menuContainer = typeof document === "undefined" ? undefined : document.body;

  const menuGroups = useMemo(() => (
    categoryOptions
      .filter((option) => option.status === "active")
      .reduce<Array<{ root: string; options: Array<{ code: BankTransactionCategoryCode; label: string; menuLabel: string }> }>>((groups, option) => {
        const root = option.path[0] || (option.source === "custom" ? "自定义" : "系统标签");
        let group = groups.find((item) => item.root === root);
        if (!group) {
          group = { root, options: [] };
          groups.push(group);
        }
        const pathLabel = option.path.length > 0 ? option.path.join(" / ") : `${root} / ${option.label}`;
        group.options.push({
          code: option.code,
          label: option.label || option.code,
          menuLabel: pathLabel,
        });
        return groups;
      }, [])
      .map((group) => ({
        ...group,
        options: group.options.sort((left, right) => left.menuLabel.localeCompare(right.menuLabel, "zh-Hans-CN")),
      }))
  ), [categoryOptions]);

  const handleOpen = (event: MouseEvent<HTMLElement>) => {
    setAnchorEl(event.currentTarget);
  };

  const handleClose = () => {
    setAnchorEl(null);
  };

  const handleSelect = (nextCategoryCode: BankTransactionCategoryCode | null) => {
    onChange(nextCategoryCode);
    handleClose();
  };

  useEffect(() => {
    if (!open) {
      return undefined;
    }
    const frameId = window.requestAnimationFrame(() => {
      selectedOptionRef.current?.focus();
    });
    return () => window.cancelAnimationFrame(frameId);
  }, [categoryCode, open]);

  return (
    <>
      <Tooltip title={displayLabel} placement="top" enterDelay={500}>
        <ButtonBase
          aria-controls={open ? menuId : undefined}
          aria-expanded={open ? "true" : undefined}
          aria-haspopup="listbox"
          aria-label={`${rowId} 类型`}
          className={`bank-category-picker-trigger${open ? " open" : ""}`}
          onClick={handleOpen}
          type="button"
        >
          <Stack className="bank-category-picker-value" direction="row" alignItems="center" spacing={0.5}>
            <BankCategoryTag categoryCode={categoryCode} className="bank-category-picker-main-tag" label={displayLabel} />
          </Stack>
          <ArrowDropDownIcon className="bank-category-picker-icon" fontSize="small" aria-hidden="true" />
        </ButtonBase>
      </Tooltip>
      <Popover
        id={menuId}
        open={open}
        anchorEl={anchorEl}
        onClose={handleClose}
        container={menuContainer}
        anchorOrigin={{ vertical: "bottom", horizontal: "left" }}
        transformOrigin={{ vertical: "top", horizontal: "left" }}
        slotProps={{ paper: { className: "bank-category-picker-popover" } }}
      >
        <MenuList
          aria-label={`${rowId} 类型分类`}
          className="bank-category-picker-menu"
          role="listbox"
          dense
          disablePadding
        >
          <MenuItem
            className="bank-category-picker-option"
            aria-label="未分类"
            aria-selected={categoryCode === null}
            ref={categoryCode === null ? selectedOptionRef : undefined}
            role="option"
            selected={categoryCode === null}
            onClick={() => handleSelect(null)}
          >
            <BankCategoryTag categoryCode={null} label="未分类" />
          </MenuItem>
          {menuGroups.map((group) => (
            <li className="bank-category-picker-section" key={group.root}>
              <ul className="bank-category-picker-section-list">
                <ListSubheader className="bank-category-picker-group">{group.root}</ListSubheader>
                {group.options.map((option) => (
                  <MenuItem
                    className="bank-category-picker-option"
                    aria-label={option.menuLabel}
                    aria-selected={categoryCode === option.code}
                    key={option.code}
                    ref={categoryCode === option.code ? selectedOptionRef : undefined}
                    role="option"
                    selected={categoryCode === option.code}
                    onClick={() => handleSelect(option.code)}
                  >
                    <BankCategoryTag categoryCode={option.code} label={option.label} />
                  </MenuItem>
                ))}
              </ul>
            </li>
          ))}
        </MenuList>
      </Popover>
    </>
  );
}
