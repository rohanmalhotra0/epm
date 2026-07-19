import { describe, expect, it } from "vitest";
import { useUi } from "../src/store/ui";

describe("ui store theme", () => {
  it("toggles between dark (g100) and light (white)", () => {
    useUi.setState({ theme: "g100" });
    useUi.getState().toggleTheme();
    expect(useUi.getState().theme).toBe("white");
    useUi.getState().toggleTheme();
    expect(useUi.getState().theme).toBe("g100");
  });

  it("sets an explicit theme", () => {
    useUi.getState().setTheme("white");
    expect(useUi.getState().theme).toBe("white");
    useUi.getState().setTheme("g100");
    expect(useUi.getState().theme).toBe("g100");
  });
});
