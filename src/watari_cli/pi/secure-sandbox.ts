import { spawn, spawnSync } from "node:child_process";
import { accessSync, constants } from "node:fs";
import {
  access,
  mkdir,
  opendir,
  readFile,
  readdir,
  stat,
  writeFile,
} from "node:fs/promises";
import path from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import {
  type BashOperations,
  createBashTool,
  createEditTool,
  createFindTool,
  createGrepTool,
  createLsTool,
  createReadTool,
  createWriteTool,
  type EditOperations,
  type FindOperations,
  type GrepOperations,
  type LsOperations,
  type ReadOperations,
  type WriteOperations,
} from "@earendil-works/pi-coding-agent";
import {
  assertWorkspacePath,
  buildBubblewrapArgs,
  discoverSensitivePaths,
  isSafeWorkspace,
} from "./secure-sandbox.mjs";

const BWRAP = ["/usr/bin/bwrap", "/bin/bwrap", "/home/linuxbrew/.linuxbrew/bin/bwrap"]
  .find((candidate) => {
    try { accessSync(candidate, constants.X_OK); return true; }
    catch { return false; }
  });

function imageMime(filePath: string): string | null {
  const ext = path.extname(filePath).toLowerCase();
  if (ext === ".png") return "image/png";
  if (ext === ".jpg" || ext === ".jpeg") return "image/jpeg";
  if (ext === ".gif") return "image/gif";
  if (ext === ".webp") return "image/webp";
  return null;
}

function readOperations(workspace: string): ReadOperations {
  return {
    async readFile(filePath) {
      const allowed = await assertWorkspacePath(workspace, filePath);
      return readFile(allowed);
    },
    async access(filePath) {
      const allowed = await assertWorkspacePath(workspace, filePath);
      await access(allowed, constants.R_OK);
    },
    async detectImageMimeType(filePath) {
      const allowed = await assertWorkspacePath(workspace, filePath);
      return imageMime(allowed);
    },
  };
}

function writeOperations(workspace: string): WriteOperations {
  return {
    async writeFile(filePath, content) {
      const allowed = await assertWorkspacePath(workspace, filePath, { allowMissing: true });
      await writeFile(allowed, content, "utf8");
    },
    async mkdir(directory) {
      const allowed = await assertWorkspacePath(workspace, directory, { allowMissing: true });
      await mkdir(allowed, { recursive: true });
    },
  };
}

function editOperations(workspace: string): EditOperations {
  const reads = readOperations(workspace);
  const writes = writeOperations(workspace);
  return {
    readFile: reads.readFile,
    writeFile: writes.writeFile,
    async access(filePath) {
      const allowed = await assertWorkspacePath(workspace, filePath);
      await access(allowed, constants.R_OK | constants.W_OK);
    },
  };
}

function lsOperations(workspace: string): LsOperations {
  return {
    async exists(filePath) {
      try {
        const allowed = await assertWorkspacePath(workspace, filePath);
        await access(allowed);
        return true;
      } catch {
        return false;
      }
    },
    async stat(filePath) {
      const allowed = await assertWorkspacePath(workspace, filePath);
      return stat(allowed);
    },
    async readdir(directory) {
      const allowed = await assertWorkspacePath(workspace, directory);
      return readdir(allowed);
    },
  };
}

function grepOperations(workspace: string): GrepOperations {
  return {
    async isDirectory(filePath) {
      const allowed = await assertWorkspacePath(workspace, filePath);
      return (await stat(allowed)).isDirectory();
    },
    async readFile(filePath) {
      const allowed = await assertWorkspacePath(workspace, filePath);
      return readFile(allowed, "utf8");
    },
  };
}

function matches(relativePath: string, pattern: string): boolean {
  const normalized = relativePath.split(path.sep).join(path.posix.sep);
  const candidate = pattern.includes("/") ? normalized : path.posix.basename(normalized);
  return path.posix.matchesGlob(candidate, pattern) ||
    (pattern.includes("/") && path.posix.matchesGlob(normalized, `**/${pattern}`));
}

function findOperations(workspace: string): FindOperations {
  return {
    async exists(filePath) {
      try {
        const allowed = await assertWorkspacePath(workspace, filePath);
        await access(allowed);
        return true;
      } catch {
        return false;
      }
    },
    async glob(pattern, root, options) {
      const allowedRoot = await assertWorkspacePath(workspace, root);
      const results: string[] = [];
      async function walk(directory: string) {
        if (results.length >= options.limit) return;
        const handle = await opendir(directory);
        for await (const entry of handle) {
          if (results.length >= options.limit) break;
          if (entry.name === ".git" || entry.name === "node_modules") continue;
          const candidate = path.join(directory, entry.name);
          if (entry.isDirectory() && !entry.isSymbolicLink()) {
            await walk(candidate);
            continue;
          }
          if (!entry.isFile()) continue;
          const checked = await assertWorkspacePath(workspace, candidate);
          const relative = path.relative(allowedRoot, checked);
          if (matches(relative, pattern)) results.push(checked);
        }
      }
      await walk(allowedRoot);
      return results;
    },
  };
}

function sandboxedBashOperations(workspace: string): BashOperations {
  return {
    async exec(command, _cwd, { onData, signal, timeout }) {
      const sensitive = await discoverSensitivePaths(workspace);
      const args = await buildBubblewrapArgs(workspace, sensitive);
      return new Promise((resolve, reject) => {
        if (signal?.aborted) {
          reject(new Error("aborted"));
          return;
        }
        if (!BWRAP) {
          reject(new Error("bubblewrap is unavailable"));
          return;
        }
        const child = spawn(BWRAP, [...args, "/bin/bash", "-lc", command], {
          detached: true,
          stdio: ["ignore", "pipe", "pipe"],
        });
        let timedOut = false;
        const stop = () => {
          if (!child.pid) return;
          try { process.kill(-child.pid, "SIGKILL"); }
          catch { child.kill("SIGKILL"); }
        };
        const timer = timeout && timeout > 0
          ? setTimeout(() => { timedOut = true; stop(); }, timeout * 1000)
          : undefined;
        const onAbort = () => stop();
        signal?.addEventListener("abort", onAbort, { once: true });
        child.stdout?.on("data", onData);
        child.stderr?.on("data", onData);
        child.on("error", (error) => {
          if (timer) clearTimeout(timer);
          signal?.removeEventListener("abort", onAbort);
          reject(error);
        });
        child.on("close", (code) => {
          if (timer) clearTimeout(timer);
          signal?.removeEventListener("abort", onAbort);
          if (signal?.aborted) reject(new Error("aborted"));
          else if (timedOut) reject(new Error(`timeout:${timeout}`));
          else resolve({ exitCode: code });
        });
      });
    },
  };
}

export default function (pi: ExtensionAPI) {
  const workspace = process.cwd();
  const supported = process.platform === "linux" && isSafeWorkspace(workspace) && Boolean(BWRAP) &&
    spawnSync(BWRAP!, ["--version"], { stdio: "ignore" }).status === 0;

  const localRead = createReadTool(workspace);
  const localWrite = createWriteTool(workspace);
  const localEdit = createEditTool(workspace);
  const localLs = createLsTool(workspace);
  const localGrep = createGrepTool(workspace);
  const localFind = createFindTool(workspace);
  const localBash = createBashTool(workspace, { exposeSessionEnvironment: false });

  function requireSandbox() {
    if (!supported) throw new Error(
      "Secure tool sandbox is unavailable or the working directory is too broad. " +
      "Start watari chat inside a specific project folder on Linux with bubblewrap installed.",
    );
  }

  pi.registerTool({
    ...localRead,
    label: "read (isolated)",
    async execute(id, params, signal, onUpdate) {
      requireSandbox();
      return createReadTool(workspace, { operations: readOperations(workspace) })
        .execute(id, params, signal, onUpdate);
    },
  });
  pi.registerTool({
    ...localWrite,
    label: "write (isolated)",
    async execute(id, params, signal, onUpdate) {
      requireSandbox();
      return createWriteTool(workspace, { operations: writeOperations(workspace) })
        .execute(id, params, signal, onUpdate);
    },
  });
  pi.registerTool({
    ...localEdit,
    label: "edit (isolated)",
    async execute(id, params, signal, onUpdate) {
      requireSandbox();
      return createEditTool(workspace, { operations: editOperations(workspace) })
        .execute(id, params, signal, onUpdate);
    },
  });
  pi.registerTool({
    ...localLs,
    label: "ls (isolated)",
    async execute(id, params, signal, onUpdate) {
      requireSandbox();
      return createLsTool(workspace, { operations: lsOperations(workspace) })
        .execute(id, params, signal, onUpdate);
    },
  });
  pi.registerTool({
    ...localGrep,
    label: "grep (isolated)",
    async execute(id, params, signal, onUpdate) {
      requireSandbox();
      return createGrepTool(workspace, { operations: grepOperations(workspace) })
        .execute(id, params, signal, onUpdate);
    },
  });
  pi.registerTool({
    ...localFind,
    label: "find (isolated)",
    async execute(id, params, signal, onUpdate) {
      requireSandbox();
      return createFindTool(workspace, { operations: findOperations(workspace) })
        .execute(id, params, signal, onUpdate);
    },
  });
  pi.registerTool({
    ...localBash,
    label: "bash (isolated, offline)",
    async execute(id, params, signal, onUpdate) {
      requireSandbox();
      return createBashTool(workspace, {
        operations: sandboxedBashOperations(workspace),
        exposeSessionEnvironment: false,
      }).execute(id, params, signal, onUpdate);
    },
  });

  pi.on("user_bash", () => {
    requireSandbox();
    return { operations: sandboxedBashOperations(workspace) };
  });

  pi.on("session_start", (_event, ctx) => {
    if (!supported) {
      ctx.ui.setStatus("watari-sandbox", ctx.ui.theme.fg("error", "🔒 隔離: 利用不可"));
      ctx.ui.notify(
        "安全な道具の隔離を開始できません。特定のプロジェクトフォルダから起動してください。",
        "error",
      );
      return;
    }
    ctx.ui.setStatus("watari-sandbox", ctx.ui.theme.fg("accent", "🔒 隔離中・通信なし"));
  });

  pi.on("before_agent_start", (event) => {
    const line = `Current working directory: ${workspace} ` +
      `(isolated workspace; network and host credentials unavailable)`;
    return { systemPrompt: `${event.systemPrompt}\n\n${line}` };
  });
}
