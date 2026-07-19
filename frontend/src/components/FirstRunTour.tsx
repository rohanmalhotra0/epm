// One-time first-run tour. Shown until the user skips or finishes it, at which
// point a localStorage flag suppresses it forever.

import { useState } from "react";
import { Button } from "@carbon/react";

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

export function FirstRunTour() {
  const [open, setOpen] = useState(() => !flagSet());
  const [step, setStep] = useState(0);

  if (!open) return null;

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
    <div className="tour-overlay" role="dialog" aria-modal="true" aria-label="Welcome tour">
      <div className="tour-card">
        <div className="tour-step">
          Step {step + 1} of {STEPS.length}
        </div>
        <h3>{s.title}</h3>
        <div className="tour-body">{s.body}</div>
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
            <Button kind="primary" size="sm" onClick={dismiss}>
              Done
            </Button>
          ) : (
            <Button kind="primary" size="sm" onClick={() => setStep((n) => n + 1)}>
              Next
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
