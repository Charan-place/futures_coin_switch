import { spawn } from "child_process";
import path from "path";
import fs from "fs";
import os from "os";

const BOT_DIR = path.resolve(process.cwd(), "..");
const VENV_PY = path.join(BOT_DIR, "venv/bin/python");
const PYTHON = fs.existsSync(VENV_PY) ? VENV_PY : "python3";

const PID_FILE = path.join(os.tmpdir(), "coin-bot.pid");
const MODE_FILE = path.join(os.tmpdir(), "coin-bot.mode");
const STARTED_FILE = path.join(os.tmpdir(), "coin-bot.started");
const BALANCE_FILE = path.join(os.tmpdir(), "coin-bot.balance");

function isRunning(pid: number): boolean {
  try { process.kill(pid, 0); return true; } catch { return false; }
}

function cleanup() {
  [PID_FILE, MODE_FILE, STARTED_FILE, BALANCE_FILE].forEach((f) => { try { fs.unlinkSync(f); } catch { /* ok */ } });
}

export function status() {
  try {
    if (!fs.existsSync(PID_FILE)) return { running: false, pid: null, mode: null, startedAt: null };
    const pid = parseInt(fs.readFileSync(PID_FILE, "utf-8").trim(), 10);
    if (!pid || !isRunning(pid)) { cleanup(); return { running: false, pid: null, mode: null, startedAt: null }; }
    return {
      running: true,
      pid,
      mode: fs.existsSync(MODE_FILE) ? fs.readFileSync(MODE_FILE, "utf-8").trim() : null,
      startedAt: fs.existsSync(STARTED_FILE) ? fs.readFileSync(STARTED_FILE, "utf-8").trim() : null,
      balance: fs.existsSync(BALANCE_FILE) ? parseFloat(fs.readFileSync(BALANCE_FILE, "utf-8").trim()) : null,
    };
  } catch { return { running: false, pid: null, mode: null, startedAt: null }; }
}

export function startBot(m: "paper" | "live", balance = 1000) {
  if (status().running) throw new Error("Bot already running");

  const proc = spawn(PYTHON, ["main.py", `--${m}`, "--balance", String(balance)], {
    cwd: BOT_DIR,
    stdio: "ignore",
    detached: true, // survives web server restarts and navigation
  });
  proc.unref();

  if (!proc.pid) throw new Error("Failed to spawn process");

  fs.writeFileSync(PID_FILE, String(proc.pid));
  fs.writeFileSync(MODE_FILE, m);
  fs.writeFileSync(STARTED_FILE, new Date().toISOString());
  fs.writeFileSync(BALANCE_FILE, String(balance));

  return status();
}

export function stopBot() {
  const s = status();
  if (!s.running || !s.pid) throw new Error("Bot not running");
  try { process.kill(s.pid, "SIGTERM"); } catch { /* already gone */ }
  cleanup();
}
