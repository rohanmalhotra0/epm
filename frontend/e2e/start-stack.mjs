import { spawn, spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const composeFile = path.resolve(here, "../../docker-compose.e2e.yml");
const composeBase = [
  "compose",
  "--project-name",
  "epmw-e2e",
  "--file",
  composeFile,
];

let stopping = false;
const stack = spawn(
  "docker",
  [
    ...composeBase,
    "up",
    "--build",
    "--force-recreate",
    "--remove-orphans",
  ],
  { stdio: "inherit" },
);

function stop(exitCode = 0) {
  if (stopping) return;
  stopping = true;
  if (!stack.killed) stack.kill("SIGTERM");
  spawnSync(
    "docker",
    [...composeBase, "down", "--remove-orphans", "--timeout", "10"],
    { stdio: "inherit" },
  );
  process.exit(exitCode);
}

process.on("SIGINT", () => stop(130));
process.on("SIGTERM", () => stop(0));
process.on("SIGHUP", () => stop(0));

stack.on("error", (error) => {
  console.error(`Could not start the isolated E2E stack: ${error.message}`);
  stop(1);
});
stack.on("exit", (code, signal) => {
  if (!stopping) {
    if (code !== 0) {
      console.error(`The isolated E2E stack exited (${signal || code || 0}).`);
    }
    stop(code ?? 1);
  }
});
