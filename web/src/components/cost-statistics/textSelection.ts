export function hasSelectedTextWithin(element: Element) {
  const selection = element.ownerDocument.getSelection();
  if (!selection || selection.isCollapsed || !selection.toString().trim()) {
    return false;
  }
  return Boolean(
    (selection.anchorNode && element.contains(selection.anchorNode))
    || (selection.focusNode && element.contains(selection.focusNode)),
  );
}
