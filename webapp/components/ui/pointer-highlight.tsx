"use client";

import React, { useRef, useState, useLayoutEffect, useEffect } from "react";
import {
  motion,
  useInView,
  AnimatePresence,
  useMotionValue,
  useSpring,
} from "motion/react";
import { cn } from "@/lib/utils";

interface PointerHighlightProps {
  children: React.ReactNode;
  rectangleClassName?: string;
  pointerClassName?: string;
  containerClassName?: string;
}

export function PointerHighlight({
  children,
  rectangleClassName,
  pointerClassName,
  containerClassName,
}: PointerHighlightProps) {
  const ref = useRef<HTMLSpanElement>(null);
  const isInView = useInView(ref, { once: true, margin: "-100px" });
  const [rectStyle, setRectStyle] = useState<{ width: number; height: number } | null>(null);
  const pointerX = useMotionValue(0);
  const pointerY = useMotionValue(0);
  const springX = useSpring(pointerX, { stiffness: 360, damping: 32, mass: 0.7 });
  const springY = useSpring(pointerY, { stiffness: 360, damping: 32, mass: 0.7 });
  const [userInteracting, setUserInteracting] = useState(false);
  const autopilotFrame = useRef<number | null>(null);
  const [autopilotDone, setAutopilotDone] = useState(false);

  useLayoutEffect(() => {
    function updateRect() {
      if (ref.current) {
        setRectStyle({
          width: ref.current.offsetWidth,
          height: ref.current.offsetHeight,
        });
      }
    }

    if (ref.current) {
      updateRect();
      const resizeObserver = new ResizeObserver(updateRect);
      resizeObserver.observe(ref.current);
      return () => resizeObserver.disconnect();
    }
  }, [children]);

  const highlightStyle = rectStyle
    ? {
        width: rectStyle.width + 16,
        height: rectStyle.height + 16,
        left: -8,
        top: -8,
      }
    : undefined;

  useEffect(() => {
    if (!rectStyle || userInteracting || autopilotDone || !isInView) return;

    const sweep = Math.max(28, rectStyle.width * 0.45);
    const wiggle = Math.max(4, rectStyle.height * 0.035);
    const duration = 3200;
    const start = performance.now();

    const easeInOutCubic = (t: number) =>
      t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;

    const step = (now: number) => {
      const t = Math.min(1, (now - start) / duration);
      const eased = easeInOutCubic(t);
      pointerX.set(-sweep + eased * sweep * 2);
      pointerY.set(Math.sin(t * Math.PI * 1.5) * wiggle);

      if (t < 1) {
        autopilotFrame.current = requestAnimationFrame(step);
      } else {
        pointerX.set(0);
        pointerY.set(0);
        setAutopilotDone(true);
        autopilotFrame.current = null;
      }
    };

    autopilotFrame.current = requestAnimationFrame(step);
    return () => {
      if (autopilotFrame.current) cancelAnimationFrame(autopilotFrame.current);
      autopilotFrame.current = null;
    };
  }, [rectStyle, userInteracting, autopilotDone, isInView, pointerX, pointerY]);

  function handlePointerMove(event: React.PointerEvent<HTMLSpanElement>) {
    if (!ref.current) return;
    if (!userInteracting) setUserInteracting(true);
    const rect = ref.current.getBoundingClientRect();
    const offsetX = event.clientX - (rect.left + rect.width / 2);
    const offsetY = event.clientY - (rect.top + rect.height / 2);
    // Translate a small amount relative to pointer position for a drag-like feel.
    pointerX.set(offsetX * 0.12);
    pointerY.set(offsetY * 0.12);
  }

  function handlePointerLeave() {
    setUserInteracting(false);
    pointerX.set(0);
    pointerY.set(0);
  }

  return (
    <span
      ref={ref}
      className={cn("relative inline-block touch-none", containerClassName)}
      onPointerMove={handlePointerMove}
      onPointerLeave={handlePointerLeave}
    >
      {children}
      <AnimatePresence>
        {isInView && (
          <>
            {/* Animated border rectangle */}
            <motion.span
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.9 }}
              transition={{ duration: 0.3, delay: 0.1 }}
              className={cn(
                "pointer-events-none absolute rounded-md border border-neutral-300/80 bg-neutral-100/70 shadow-[0_16px_50px_-28px_rgba(0,0,0,0.65)] backdrop-blur-sm -z-10 dark:border-neutral-700/70 dark:bg-neutral-900/40",
                rectangleClassName
              )}
              style={{
                ...highlightStyle,
                x: springX,
                y: springY,
              }}
            />
            {/* Pointer cursor */}
            <motion.span
              initial={{ opacity: 0, x: -18, y: -18 }}
              animate={{ opacity: 1, x: 0, y: 0 }}
              exit={{ opacity: 0 }}
              transition={{
                duration: 0.4,
                delay: 0.15,
                type: "spring",
                stiffness: 220,
                damping: 22,
              }}
              className={cn(
                "pointer-events-none absolute -right-5 -top-5 z-10 text-amber-400 drop-shadow-[0_6px_16px_rgba(0,0,0,0.25)]",
                pointerClassName
              )}
              style={{ x: springX, y: springY }}
            >
              <svg
                width="24"
                height="24"
                viewBox="0 0 24 24"
                fill="currentColor"
                className="h-6 w-6 -rotate-12 drop-shadow-[0_4px_10px_rgba(0,0,0,0.25)]"
              >
                <path d="M4.2 3.1l15.5 9.3c.7.4.5 1.5-.3 1.7l-6.2 1.7-1.6 4.8c-.3.8-1.4.9-1.8.1L3.5 4.4c-.3-.7.5-1.4 1.2-.9z" />
              </svg>
            </motion.span>
          </>
        )}
      </AnimatePresence>
    </span>
  );
}

export default PointerHighlight;
