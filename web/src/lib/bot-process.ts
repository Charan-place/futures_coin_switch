import { spawn, type ChildProcess } from "child_process";
import path from "path";
import fs from "fs";

const BOT_DIR = path.resolve(process.cwd(), "..");
const VENV_PY = path.join(BOT_DIR, "venv/bin/python");
const PYTHON = fs.existsSync(VENV_PY) ? VENV_PY : "python3";

let proc: ChildProcess | null = null;
let mode: "paper" | "live" | null = null;
let startedAt: Date | null = null;

export function startBot(m: "paper" | "live") {
  if (proc) throw new Error("Bot already running");

  proc = spawn(PYTHON, ["main.py", `--${m}`], {
    cwd: BOT_DIR,
    stdio: "pipe",
    detached: false,
  });

  mode = m;
  startedAt = new Date();

  proc.on("exit", () => {
    proc = null;
    mode = null;
    startedAt = null;
  });

  return status();
}

export function stopBot() {
  if (!proc) throw new Error("Bot not running");
  proc.kill("SIGTERM");
  proc = null;
  mode = null;
  startedAt = null;
}

export function status() {
  return {
    running: proc !== null,
    pid: proc?.pid ?? null,
    mode,
    startedAt: startedAt?.toISOString() ?? null,
  };
}
