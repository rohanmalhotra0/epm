import { useEffect, useLayoutEffect, useRef, useState } from "react";

/**
 * Motion primitives shared by the public landing (/) and docs (/docs) pages.
 *
 * Design rule (see the landing/docs CSS): content is NEVER gated behind JS or
 * motion. The default CSS renders every element at its final, readable state.
 * Animation is *additive* — a `reveal-on` marker class is applied to the scroll
 * container ONLY when JavaScript is running AND the visitor has not asked for
 * reduced motion. The "start hidden" styles are scoped under `.reveal-on`, so:
 *   - reduced-motion visitors never get `.reveal-on` → everything shows at rest;
 *   - if JS never runs, `.reveal-on` is absent → everything shows at rest.
 * Only when motion is welcome do elements begin hidden and animate into view.
 */

const REDUCE_QUERY = "(prefers-reduced-motion: reduce)";

function prefersReduced(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia(REDUCE_QUERY).matches
  );
}

/** Reactive `prefers-reduced-motion` flag; updates if the OS setting changes. */
export function usePrefersReducedMotion(): boolean {
  const [reduce, setReduce] = useState<boolean>(prefersReduced);
  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") return;
    const mq = window.matchMedia(REDUCE_QUERY);
    const onChange = () => setReduce(mq.matches);
    onChange();
    // Safari <14 only supports the deprecated addListener signature.
    mq.addEventListener?.("change", onChange);
    return () => mq.removeEventListener?.("change", onChange);
  }, []);
  return reduce;
}

/**
 * Scroll-reveal controller. Attach the returned ref to a scroll container; any
 * descendant carrying `data-reveal` fades/rises into place the first time it
 * enters the viewport (via a `.in-view` class), staggered by its inline `--i`.
 *
 * The `reveal-on` class is added in a layout effect (before paint) to avoid a
 * flash of the not-yet-hidden content. When motion is reduced or
 * IntersectionObserver is unavailable, the class is never added and no observer
 * runs — the elements simply render at their final state.
 */
export function useScrollReveal<T extends HTMLElement = HTMLDivElement>() {
  const ref = useRef<T>(null);

  useLayoutEffect(() => {
    const root = ref.current;
    if (!root) return;
    if (prefersReduced() || typeof IntersectionObserver === "undefined") return;

    root.classList.add("reveal-on");
    const targets = Array.from(root.querySelectorAll<HTMLElement>("[data-reveal]"));
    if (targets.length === 0) return;

    const io = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            entry.target.classList.add("in-view");
            io.unobserve(entry.target);
          }
        }
      },
      { threshold: 0.15, rootMargin: "0px 0px -8% 0px" },
    );
    targets.forEach((t) => io.observe(t));
    return () => io.disconnect();
  }, []);

  return ref;
}
