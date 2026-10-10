import { createContext, useCallback, useContext, useLayoutEffect, useRef, useState, type ReactNode } from 'react';

type MotionCells = { register: (node: HTMLDivElement) => () => void };
const MotionContext = createContext<MotionCells | null>(null);
export const useRelationMotion = () => useContext(MotionContext);

// No extra table, row or cell: every member stays in the original column grid.
export default function RelationRowsMotion({ expanded, onExited, children }: {
  expanded: boolean; onExited: () => void; children: ReactNode;
}) {
  const cells = useRef(new Set<HTMLDivElement>());
  const startedCells = useRef(new WeakSet<HTMLDivElement>());
  const [revision, setRevision] = useState(0);
  const exit = useRef(onExited);
  exit.current = onExited;
  const register = useCallback((node: HTMLDivElement) => {
    cells.current.add(node);
    setRevision(value => value + 1);
    return () => { cells.current.delete(node); };
  }, []);
  useLayoutEffect(() => {
    const nodes = [...cells.current];
    if (!nodes.length) return;
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const frames = nodes.map(node => {
      const frame = { node, from: startedCells.current.has(node) ? node.getBoundingClientRect().height : 0, to: node.scrollHeight };
      startedCells.current.add(node);
      return frame;
    });
    if (reduced) {
      nodes.forEach(node => { node.style.height = expanded ? 'auto' : '0px'; });
      if (!expanded) exit.current();
      return;
    }
    const animations = frames.map(({ node, from, to }) => {
      node.style.height = expanded ? 'auto' : '0px';
      return node.animate([{ height: `${from}px` }, { height: expanded ? `${to}px` : '0px' }], {
        duration: expanded ? 220 : 170, easing: 'cubic-bezier(.2,.7,.2,1)',
      });
    });
    let remaining = animations.length;
    animations.forEach(animation => {
      animation.onfinish = () => { if (--remaining === 0 && !expanded) exit.current(); };
    });
    return () => {
      // Capture all current heights before cancelling; rapid reversals start here.
      const heights = nodes.map(node => node.getBoundingClientRect().height);
      nodes.forEach((node, index) => { node.style.height = `${heights[index]}px`; });
      animations.forEach(animation => { animation.onfinish = null; animation.cancel(); });
    };
  }, [expanded, revision]);
  return <MotionContext.Provider value={{ register }}>{children}</MotionContext.Provider>;
}

export function RelationAnimatedCell({ children, motion: capturedMotion }: { children: ReactNode; motion?: MotionCells | null }) {
  const currentMotion = useRelationMotion();
  const motion = capturedMotion === undefined ? currentMotion : capturedMotion;
  const ref = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    if (!motion || !ref.current) return;
    const node = ref.current;
    const cell = node.parentElement!;
    const content = node.firstElementChild as HTMLElement;
    const style = getComputedStyle(cell);
    content.style.padding = `${style.paddingTop} ${style.paddingRight} ${style.paddingBottom} ${style.paddingLeft}`;
    cell.classList.add('relation-motion-cell');
    const unregister = motion.register(node);
    return () => { unregister(); cell.classList.remove('relation-motion-cell'); };
  }, [motion?.register]);
  return motion ? <div className="relation-motion-clip" ref={ref}><div className="relation-motion-content">{children}</div></div> : <>{children}</>;
}
