import { useLayoutEffect, useRef, type ReactNode } from "react";

/** Same native slide timings as ordinary relation rows, scoped to batch bodies. */
export default function BatchExpansion({ children, contentKey, expanded, id, label, onExited }: {
  children: ReactNode;
  contentKey: string;
  expanded: boolean;
  id: string;
  label: string;
  onExited: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const started = useRef(false);
  const exited = useRef(onExited);
  exited.current = onExited;

  useLayoutEffect(() => {
    const node = ref.current!;
    const content = contentRef.current!;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduced) {
      started.current = true;
      node.style.height = expanded ? "auto" : "0px";
      node.style.opacity = expanded ? "1" : "0.6";
      if (!expanded) exited.current();
      return;
    }

    let animation: Animation | null = null;
    let frame: number | null = null;
    let lastTargetHeight = -1;
    if (!started.current) {
      node.style.height = "0px";
      node.style.opacity = "0.6";
      started.current = true;
    }

    const slideTo = (height: number) => {
      if (height === lastTargetHeight) return;
      const startHeight = node.getBoundingClientRect().height;
      const startOpacity = Number(getComputedStyle(node).opacity);
      node.style.height = `${startHeight}px`;
      node.style.opacity = String(startOpacity);
      animation?.cancel();
      lastTargetHeight = height;
      animation = node.animate([
        { height: `${startHeight}px`, opacity: startOpacity },
        { height: `${height}px`, opacity: expanded ? 1 : 0.6 },
      ], { duration: expanded ? 220 : 170, easing: "cubic-bezier(.2,.7,.2,1)", fill: "forwards" });
      const currentAnimation = animation;
      animation.onfinish = () => {
        if (animation !== currentAnimation) return;
        node.style.height = expanded ? "auto" : "0px";
        node.style.opacity = expanded ? "1" : "0.6";
        animation.cancel();
        animation = null;
        if (!expanded) exited.current();
      };
    };

    const measureOnFrame = () => {
      if (frame !== null) return;
      frame = requestAnimationFrame(() => {
        frame = null;
        // HeroUI Table builds its collection after mounting. Measure the natural
        // inner content after layout, never the clipped animated outer height.
        slideTo(content.getBoundingClientRect().height);
      });
    };
    const observer = new ResizeObserver(() => {
      if (expanded) measureOnFrame();
    });
    if (expanded) {
      observer.observe(content);
      measureOnFrame();
    } else {
      slideTo(0);
    }

    return () => {
      observer.disconnect();
      if (frame !== null) cancelAnimationFrame(frame);
      // Preserve the visible frame when reversing or when async content changes.
      node.style.height = `${node.getBoundingClientRect().height}px`;
      node.style.opacity = getComputedStyle(node).opacity;
      animation?.cancel();
    };
  }, [expanded, contentKey]);

  return <div ref={ref} id={id} className="bank-flow-rule-batches-expansion" data-expanded={expanded} inert={!expanded}>
    <div ref={contentRef} role="region" aria-label={label} className="bank-flow-rule-batches-expansion__content">{children}</div>
  </div>;
}
