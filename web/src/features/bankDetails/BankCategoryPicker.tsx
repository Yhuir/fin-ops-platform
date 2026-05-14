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
import { CATEGORY_LABEL_BY_CODE, CATEGORY_TREE } from "./categoryOptions";
import type { BankTransactionCategoryCode } from "./types";

type BankCategoryPickerProps = {
  rowId: string;
  categoryCode: BankTransactionCategoryCode | null;
  categoryLabel: string | null;
  categorySource: string;
  onChange: (categoryCode: BankTransactionCategoryCode | null) => void;
};

function getCategoryLabel(categoryCode: BankTransactionCategoryCode | null, categoryLabel: string | null) {
  if (!categoryCode) {
    return "未分类";
  }
  return categoryLabel?.trim() || CATEGORY_LABEL_BY_CODE[categoryCode] || categoryCode;
}

export default function BankCategoryPicker({
  rowId,
  categoryCode,
  categoryLabel,
  onChange,
}: BankCategoryPickerProps) {
  const menuId = useId();
  const [anchorEl, setAnchorEl] = useState<HTMLElement | null>(null);
  const selectedOptionRef = useRef<HTMLLIElement | null>(null);
  const open = Boolean(anchorEl);
  const displayLabel = getCategoryLabel(categoryCode, categoryLabel);
  const menuContainer = typeof document === "undefined" ? undefined : document.body;

  const menuGroups = useMemo(() => (
    CATEGORY_TREE.map((rootNode) => ({
      root: rootNode.root,
      options: rootNode.groups.flatMap((group) => (
        group.items.map((item) => ({
          code: item.code,
          label: item.label ?? CATEGORY_LABEL_BY_CODE[item.code] ?? item.code,
          menuLabel: item.menuLabel ?? `${rootNode.root} / ${group.name} / ${item.status}`,
        }))
      )),
    }))
  ), []);

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
