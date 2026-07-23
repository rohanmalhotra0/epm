import { useEffect, type RefObject } from "react";

/**
 * Hide and disable every branch behind a modal without assuming where the
 * component primitive places the dialog in the app shell. The modal primitive
 * remains responsible for focus trapping and dismissal.
 */
export function useInertAppBackground(
  modalRef: RefObject<HTMLElement>,
  active = true,
) {
  useEffect(() => {
    if (!active) return;

    const modal = modalRef.current;
    const appShell = modal?.closest<HTMLElement>(".app-shell");
    if (!modal || !appShell) return;

    const background: HTMLElement[] = [];
    let branch: HTMLElement = modal;

    while (branch !== appShell && branch.parentElement) {
      const parent = branch.parentElement;
      for (const sibling of Array.from(parent.children)) {
        if (sibling !== branch && sibling instanceof HTMLElement) {
          background.push(sibling);
        }
      }
      branch = parent;
    }

    const previous = background.map((element) => ({
      element,
      ariaHidden: element.getAttribute("aria-hidden"),
      inert: element.inert,
      hadInertAttribute: element.hasAttribute("inert"),
    }));

    for (const element of background) {
      element.inert = true;
      element.setAttribute("inert", "");
      element.setAttribute("aria-hidden", "true");
    }

    return () => {
      for (const state of previous) {
        state.element.inert = state.inert;
        if (!state.hadInertAttribute) {
          state.element.removeAttribute("inert");
        }
        if (state.ariaHidden === null) {
          state.element.removeAttribute("aria-hidden");
        } else {
          state.element.setAttribute("aria-hidden", state.ariaHidden);
        }
      }
    };
  }, [active, modalRef]);
}
