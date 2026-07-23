// One-time first-run tour. Shown until the user skips or finishes it, at which
// point a localStorage flag suppresses it forever.

import { useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { Button, ComposedModal } from "@carbon/react";
import { useEnvironments } from "../api/hooks";
import { useUi } from "../store/ui";

export const TOUR_FLAG = "epmw-tour-done";

const STEPS = [
  {
    title: "Welcome to EPM Wizard",
    body: (
      <>
        <p>Build, inspect and deploy EPM artifacts by chatting. Try one of these to start:</p>
        <div className="tour-prompt">Create an Actuals form with level-zero descendants of Total Payroll in rows</div>
        <div className="tour-prompt">Visualize OEP_DCSH</div>
      </>
    ),
  },
  {
    title: "Sidebar & pages",
    body: (
      <p>
        The sidebar keeps your conversations, and links to Contexts, Artifacts, Deployments, Skills, Explorer, Data and
        Settings. Everything you build in chat lands on those pages.
      </p>
    ),
  },
  {
    title: "Command palette",
    body: (
      <p>
        Press <kbd>Ctrl/Cmd</kbd>+<kbd>K</kbd> to search everything or jump anywhere. <kbd>Ctrl/Cmd</kbd>+
        <kbd>Shift</kbd>+<kbd>O</kbd> starts a new chat, and <kbd>Ctrl/Cmd</kbd>+<kbd>/</kbd> focuses the message box.
      </p>
    ),
  },
];

function flagSet(): boolean {
  try {
    return !!localStorage.getItem(TOUR_FLAG);
  } catch {
    return true; // no storage → don't nag on every load
  }
}

/**
 * Carbon traps focus inside its modal, while this hides the rest of the app
 * from pointer interaction and the accessibility tree. Walk each ancestor so
 * siblings such as the sidebar, header and command palette are all covered.
 */
function useInertAppBackground(modalRef: React.RefObject<HTMLDivElement>, active: boolean) {
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

export function FirstRunTour() {
  const [open, setOpen] = useState(() => !flagSet());
  const [step, setStep] = useState(0);
  const modalRef = useRef<HTMLDivElement>(null);
  const projectId = useUi((s) => s.currentProjectId) ?? undefined;
  const gateSkipped = useUi((s) => s.oracleGateSkipped);
  const { pathname } = useLocation();
  const { data: environments = [], isLoading } = useEnvironments(projectId);
  const connected = environments.some((environment) => environment.connected);
  const gateResolved = !!projectId && !isLoading && (connected || gateSkipped);
  const tourOpen = open && gateResolved && pathname !== "/settings";

  useInertAppBackground(modalRef, tourOpen);

  // Opening Settings is allowed while gated, but it should not trigger the
  // product tour before the user connects or explicitly continues offline.
  if (!tourOpen) return null;

  const dismiss = () => {
    try {
      localStorage.setItem(TOUR_FLAG, "1");
    } catch {
      /* ignore */
    }
    setOpen(false);
  };

  const last = step === STEPS.length - 1;
  const s = STEPS[step];

  return (
    <ComposedModal
      ref={modalRef}
      open
      size="sm"
      className="tour-overlay"
      containerClassName="tour-card"
      aria-labelledby="first-run-tour-title"
      selectorPrimaryFocus="[data-tour-primary-focus]"
      preventCloseOnClickOutside
      onClose={() => false}
    >
      <div className="tour-step" aria-live="polite">
        Step {step + 1} of {STEPS.length}
      </div>
      <h3 id="first-run-tour-title" className="text-balance">
        {s.title}
      </h3>
      <div className="tour-body text-pretty">{s.body}</div>
      <div className="tour-actions">
        <Button kind="ghost" size="sm" onClick={dismiss}>
          Skip tour
        </Button>
        <span className="spacer" />
        {step > 0 && (
          <Button kind="secondary" size="sm" onClick={() => setStep((n) => n - 1)}>
            Back
          </Button>
        )}
        {last ? (
          <Button data-tour-primary-focus kind="primary" size="sm" onClick={dismiss}>
            Done
          </Button>
        ) : (
          <Button data-tour-primary-focus kind="primary" size="sm" onClick={() => setStep((n) => n + 1)}>
            Next
          </Button>
        )}
      </div>
    </ComposedModal>
  );
}
