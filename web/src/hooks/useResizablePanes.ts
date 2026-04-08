import { useCallback, useEffect, useMemo, useState } from "react";

const DEFAULT_WIDTHS = [0.32, 0.36, 0.32];
const COLLAPSE_EPSILON = 0.0001;
const SNAP_THRESHOLD = 0.06;

type DragState = {
  leftIndex: number;
  rightIndex: number;
  startClientX: number;
  startWidths: number[];
  containerWidth: number;
};

function roundWidth(value: number) {
  return Number(value.toFixed(4));
}

function redistributeWidths(widths: number[], targetIndex: number) {
  const next = [...widths];
  const released = next[targetIndex];
  next[targetIndex] = 0;

  const otherIndices = next
    .map((width, index) => ({ width, index }))
    .filter(({ width, index }) => index !== targetIndex && width > COLLAPSE_EPSILON)
    .map(({ index }) => index);

  if (otherIndices.length === 0) {
    return widths;
  }

  const totalOtherWidth = otherIndices.reduce((sum, index) => sum + next[index], 0);
  otherIndices.forEach((index) => {
    const ratio = totalOtherWidth > 0 ? next[index] / totalOtherWidth : 1 / otherIndices.length;
    next[index] = roundWidth(next[index] + released * ratio);
  });

  return next;
}

function restoreWidth(widths: number[], targetIndex: number, defaultWidths: number[]) {
  const next = [...widths];
  const restoreAmount = defaultWidths[targetIndex];
  const otherIndices = next
    .map((width, index) => ({ width, index }))
    .filter(({ width, index }) => index !== targetIndex && width > COLLAPSE_EPSILON)
    .map(({ index }) => index);

  if (otherIndices.length === 0) {
    return [...defaultWidths];
  }

  const activeTotal = otherIndices.reduce((sum, index) => sum + next[index], 0);
  const remaining = 1 - restoreAmount;
  otherIndices.forEach((index) => {
    const ratio = activeTotal > 0 ? next[index] / activeTotal : 1 / otherIndices.length;
    next[index] = roundWidth(remaining * ratio);
  });
  next[targetIndex] = roundWidth(restoreAmount);

  return next;
}

export function useResizablePanes(initialWidths = DEFAULT_WIDTHS) {
  const [widths, setWidths] = useState(() => [...initialWidths]);
  const [dragState, setDragState] = useState<DragState | null>(null);

  const visibleIndices = useMemo(
    () =>
      widths
        .map((width, index) => ({ width, index }))
        .filter(({ width }) => width > COLLAPSE_EPSILON)
        .map(({ index }) => index),
    [widths],
  );

  const visibleCount = visibleIndices.length;

  useEffect(() => {
    if (!dragState) {
      return undefined;
    }

    const onPointerMove = (event: PointerEvent | MouseEvent) => {
      if (!Number.isFinite(event.clientX)) {
        return;
      }

      const deltaFraction = (event.clientX - dragState.startClientX) / Math.max(dragState.containerWidth, 1);
      const pairTotal =
        dragState.startWidths[dragState.leftIndex] + dragState.startWidths[dragState.rightIndex];
      const rawLeft = dragState.startWidths[dragState.leftIndex] + deltaFraction;
      const clampedLeft = Math.max(0, Math.min(pairTotal, rawLeft));

      let nextLeft = clampedLeft;
      let nextRight = pairTotal - clampedLeft;

      if (nextLeft <= SNAP_THRESHOLD) {
        nextLeft = 0;
        nextRight = pairTotal;
      } else if (nextRight <= SNAP_THRESHOLD) {
        nextLeft = pairTotal;
        nextRight = 0;
      }

      setWidths((currentWidths) => {
        const nextWidths = [...currentWidths];
        nextWidths[dragState.leftIndex] = roundWidth(nextLeft);
        nextWidths[dragState.rightIndex] = roundWidth(nextRight);
        return nextWidths;
      });
    };

    const onPointerUp = () => {
      setDragState(null);
    };

    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", onPointerUp);
    window.addEventListener("mousemove", onPointerMove);
    window.addEventListener("mouseup", onPointerUp);

    return () => {
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", onPointerUp);
      window.removeEventListener("mousemove", onPointerMove);
      window.removeEventListener("mouseup", onPointerUp);
    };
  }, [dragState]);

  const togglePane = useCallback((index: number) => {
    setWidths((currentWidths) => {
      if (currentWidths[index] > COLLAPSE_EPSILON) {
        const activeCount = currentWidths.filter((width) => width > COLLAPSE_EPSILON).length;
        if (activeCount <= 1) {
          return currentWidths;
        }
        return redistributeWidths(currentWidths, index);
      }

      return restoreWidth(currentWidths, index, initialWidths);
    });
  }, [initialWidths]);

  const startDrag = useCallback((leftIndex: number, rightIndex: number, clientX: number, containerWidth: number) => {
    if (!Number.isFinite(clientX)) {
      return;
    }

    setDragState({
      leftIndex,
      rightIndex,
      startClientX: clientX,
      startWidths: widths,
      containerWidth,
    });
  }, [widths]);

  return {
    widths,
    visibleIndices,
    visibleCount,
    togglePane,
    startDrag,
  };
}
