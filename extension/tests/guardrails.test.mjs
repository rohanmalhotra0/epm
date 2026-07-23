import assert from "node:assert/strict";
import test from "node:test";

import { assessAction } from "../background/guardrails.js";

test("authoritative production classification gates writes without URL hints", () => {
  const result = assessAction(
    { type: "click", ref: 4 },
    {
      label: "Save",
      url: "https://tenant.example/Planning",
      classification: "production",
    },
  );
  assert.equal(result.hold, true);
  assert.match(result.reason, /PRODUCTION/);
});

test("blind coordinate writes are gated in non-production environments", () => {
  const result = assessAction(
    { type: "click", x: 100, y: 200 },
    {
      url: "https://tenant.example/Planning",
      classification: "development",
    },
  );
  assert.equal(result.hold, true);
  assert.match(result.reason, /Coordinate-only/);
});

test("same-origin navigation is allowed but cross-origin navigation is held", () => {
  const context = {
    url: "https://tenant.example/Planning",
    allowedOrigin: "https://tenant.example",
  };
  assert.equal(
    assessAction({ type: "navigate", url: "https://tenant.example/Forms" }, context).hold,
    false,
  );
  assert.equal(
    assessAction({ type: "navigate", url: "https://attacker.example" }, context).hold,
    true,
  );
});
