import { expect, type Locator, type Page } from "@playwright/test";

export async function dragSelectVisibleText(page: Page, target: Locator) {
  await target.scrollIntoViewIfNeeded();
  const points = await target.evaluate((element) => {
    const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
    const nodes: Array<{ node: Text; start: number; end: number }> = [];
    let current = walker.nextNode();
    while (current) {
      const node = current as Text;
      const parent = node.parentElement;
      const value = node.data;
      const start = value.search(/\S/);
      if (parent && start >= 0 && !parent.closest("button, a, input, select, textarea")) {
        const trailingWhitespace = value.match(/\s+$/)?.[0].length ?? 0;
        nodes.push({ node, start, end: Math.max(start + 1, value.length - trailingWhitespace) });
      }
      current = walker.nextNode();
    }
    const first = nodes[0];
    const last = nodes[nodes.length - 1];
    if (!first || !last) return null;

    const characterRect = (node: Text, start: number, end: number) => {
      const range = document.createRange();
      range.setStart(node, start);
      range.setEnd(node, end);
      return range.getBoundingClientRect();
    };
    const startRect = characterRect(first.node, first.start, Math.min(first.start + 1, first.end));
    const endRect = characterRect(last.node, Math.max(last.start, last.end - 1), last.end);
    return {
      start: { x: startRect.left + startRect.width * 0.25, y: startRect.top + startRect.height / 2 },
      end: { x: endRect.left + endRect.width * 0.75, y: endRect.top + endRect.height / 2 },
    };
  });
  expect(points).not.toBeNull();
  if (!points) return "";

  await page.evaluate(() => window.getSelection()?.removeAllRanges());
  await page.mouse.move(points.start.x, points.start.y);
  await page.mouse.down();
  await page.mouse.move(points.end.x, points.end.y, { steps: 12 });
  await page.mouse.up();
  const selectedText = await page.evaluate(() => window.getSelection()?.toString() ?? "");
  if (!selectedText) {
    const diagnostics = await target.evaluate((element, dragPoints) => {
      const chain: Array<Record<string, string | null>> = [];
      let current: Element | null = element;
      while (current && chain.length < 10) {
        const style = getComputedStyle(current);
        chain.push({
          className: current.getAttribute("class"),
          pointerEvents: style.pointerEvents,
          role: current.getAttribute("role"),
          tagName: current.tagName,
          userSelect: style.userSelect,
          webkitUserSelect: style.webkitUserSelect,
        });
        current = current.parentElement;
      }
      const pointElement = (point: { x: number; y: number }) => {
        const found = document.elementFromPoint(point.x, point.y);
        return found ? `${found.tagName}.${found.getAttribute("class") ?? ""}` : null;
      };
      return {
        dragPoints: { start: dragPoints.start, end: dragPoints.end },
        chain,
        endElement: pointElement(dragPoints.end),
        startElement: pointElement(dragPoints.start),
      };
    }, points);
    throw new Error(`Mouse drag did not create a text selection: ${JSON.stringify(diagnostics)}`);
  }
  return selectedText;
}
