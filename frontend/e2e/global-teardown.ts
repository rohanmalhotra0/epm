import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import path from "node:path";

export default function globalTeardown() {
  if (process.env.E2E_BASE_URL) return;

  const here = path.dirname(fileURLToPath(import.meta.url));
  const composeFile = path.resolve(here, "../../docker-compose.e2e.yml");
  const result = spawnSync(
    "docker",
    [
      "compose",
      "--project-name",
      "epmw-e2e",
      "--file",
      composeFile,
      "down",
      "--remove-orphans",
      "--timeout",
      "10",
    ],
    { stdio: "inherit" },
  );

  if (result.error) {
    console.warn(`Could not stop the isolated E2E stack: ${result.error.message}`);
  }
}
