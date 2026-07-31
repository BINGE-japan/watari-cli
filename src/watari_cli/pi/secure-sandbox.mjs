import { lstat, opendir, realpath } from "node:fs/promises";
import os from "node:os";
import path from "node:path";

export const GUEST_WORKSPACE = "/tmp/watari-workspace";
export const GUEST_HOME = "/tmp/watari-home";

const SYSTEM_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin";
const SENSITIVE_PATTERNS = [
  /(^|\/)\.env(?:\..*)?$/i,
  /(^|\/)\.(?:npmrc|pypirc)$/i,
  /\.(?:pem|key|p12|pfx)$/i,
  /(^|\/)(?:credentials?|secrets?)(?:\.[^/]*)?$/i,
  /(^|\/)service[-_]?account(?:\.[^/]*)?$/i,
];

function normalized(value) {
  return path.resolve(String(value || ""));
}

export function isInsideWorkspace(workspace, candidate) {
  const root = normalized(workspace);
  const target = normalized(candidate);
  const relative = path.relative(root, target);
  return relative === "" || (!relative.startsWith("..") && !path.isAbsolute(relative));
}

export function isSafeWorkspace(workspace, home = os.homedir()) {
  const root = normalized(workspace);
  const userHome = normalized(home);
  if (root === path.parse(root).root) return false;
  if (root === userHome || isInsideWorkspace(root, userHome)) return false;
  const protectedPaths = [
    path.join(userHome, ".config"),
    path.join(userHome, ".pi"),
    path.join(userHome, ".ssh"),
    path.join(userHome, ".claude"),
    path.join(userHome, ".codex"),
    path.join(userHome, ".local", "share", "watari"),
  ];
  return !protectedPaths.some((protectedPath) => isInsideWorkspace(protectedPath, root));
}

export function isSensitiveWorkspacePath(workspace, candidate) {
  if (!isInsideWorkspace(workspace, candidate)) return true;
  const relative = path.relative(normalized(workspace), normalized(candidate)).split(path.sep).join("/");
  return SENSITIVE_PATTERNS.some((pattern) => pattern.test(relative));
}

export function resolveWorkspacePath(workspace, inputPath) {
  const value = String(inputPath || "").trim().replace(/^@/, "");
  const target = path.isAbsolute(value) ? normalized(value) : path.resolve(workspace, value || ".");
  if (!isInsideWorkspace(workspace, target)) {
    throw new Error(`Access outside the workspace is blocked: ${inputPath}`);
  }
  if (isSensitiveWorkspacePath(workspace, target)) {
    throw new Error(`Access to a sensitive project file is blocked: ${inputPath}`);
  }
  return target;
}

export async function assertWorkspacePath(workspace, inputPath, { allowMissing = false } = {}) {
  const target = resolveWorkspacePath(workspace, inputPath);
  let probe = target;
  for (;;) {
    try {
      const canonical = await realpath(probe);
      if (!isInsideWorkspace(workspace, canonical)) {
        throw new Error(`Symlink escape outside the workspace is blocked: ${inputPath}`);
      }
      return target;
    } catch (error) {
      if (error?.code !== "ENOENT") throw error;
      if (!allowMissing) throw error;
      try {
        if ((await lstat(probe)).isSymbolicLink()) {
          throw new Error(`Dangling symlink escape is blocked: ${inputPath}`);
        }
      } catch (linkError) {
        if (linkError?.code !== "ENOENT") throw linkError;
      }
      const parent = path.dirname(probe);
      if (parent === probe) throw error;
      probe = parent;
    }
  }
}

export function sandboxEnvironment(source = process.env) {
  const userHome = os.homedir();
  const safePath = [
    path.join(userHome, ".vite-plus", "bin"),
    path.join(userHome, ".local", "bin"),
    "/home/linuxbrew/.linuxbrew/bin",
    SYSTEM_PATH,
  ].join(":");
  const env = {
    HOME: GUEST_HOME,
    PATH: safePath,
    LANG: source.LANG || "C.UTF-8",
    LC_ALL: source.LC_ALL || source.LANG || "C.UTF-8",
    TERM: source.TERM || "xterm-256color",
    CI: "1",
  };
  if (source.TZ) env.TZ = source.TZ;
  return env;
}

export function guestPath(workspace, hostPath) {
  const target = normalized(hostPath);
  if (!isInsideWorkspace(workspace, target)) {
    throw new Error(`Access outside the workspace is blocked: ${hostPath}`);
  }
  const relative = path.relative(normalized(workspace), target).split(path.sep).join(path.posix.sep);
  return relative ? path.posix.join(GUEST_WORKSPACE, relative) : GUEST_WORKSPACE;
}

export async function discoverSensitivePaths(workspace, limit = 4096) {
  const found = [];
  async function walk(directory) {
    let handle;
    try {
      handle = await opendir(directory);
    } catch {
      return;
    }
    for await (const entry of handle) {
      if (entry.name === ".git" || entry.name === "node_modules") continue;
      const candidate = path.join(directory, entry.name);
      if (isSensitiveWorkspacePath(workspace, candidate)) {
        if (found.length >= limit) {
          throw new Error(`Too many sensitive project paths to mask safely (limit ${limit})`);
        }
        found.push(candidate);
        continue;
      }
      if (entry.isDirectory() && !entry.isSymbolicLink()) await walk(candidate);
    }
  }
  await walk(normalized(workspace));
  return found;
}

export async function buildBubblewrapArgs(workspace, sensitivePaths = []) {
  const root = normalized(workspace);
  if (!isSafeWorkspace(root)) {
    throw new Error(`Unsafe workspace root for sandboxing: ${root}`);
  }
  const env = sandboxEnvironment();
  const userHome = os.homedir();
  const args = [
    "--die-with-parent",
    "--unshare-all",
    "--new-session",
    "--clearenv",
    "--ro-bind", "/", "/",
    "--tmpfs", "/home",
    "--tmpfs", "/mnt",
    "--tmpfs", "/run",
    "--tmpfs", "/tmp",
    "--tmpfs", "/root",
    "--dev", "/dev",
    "--proc", "/proc",
    "--dir", GUEST_WORKSPACE,
    "--dir", GUEST_HOME,
    "--dir", userHome,
    "--dir", path.join(userHome, ".local"),
    "--dir", path.join(userHome, ".local", "share"),
    "--dir", path.join(userHome, ".local", "bin"),
    "--dir", path.join(userHome, ".local", "share", "uv"),
    "--dir", path.join(userHome, ".vite-plus"),
    "--dir", "/home/linuxbrew",
    "--dir", "/home/linuxbrew/.linuxbrew",
    "--ro-bind-try", path.join(userHome, ".local", "bin"), path.join(userHome, ".local", "bin"),
    "--ro-bind-try", path.join(userHome, ".local", "share", "uv"), path.join(userHome, ".local", "share", "uv"),
    "--ro-bind-try", path.join(userHome, ".vite-plus"), path.join(userHome, ".vite-plus"),
    "--ro-bind-try", "/home/linuxbrew/.linuxbrew", "/home/linuxbrew/.linuxbrew",
    "--bind", root, GUEST_WORKSPACE,
    "--dir", root,
    "--bind", root, root,
    "--chdir", root,
  ];
  for (const [key, value] of Object.entries(env)) args.push("--setenv", key, value);
  for (const candidate of sensitivePaths) {
    if (!isInsideWorkspace(root, candidate)) continue;
    const target = guestPath(root, candidate);
    let stat;
    try {
      stat = await lstat(candidate);
    } catch {
      continue;
    }
    const originalTarget = normalized(candidate);
    if (stat.isDirectory()) {
      args.push("--tmpfs", target, "--tmpfs", originalTarget);
    } else {
      args.push("--ro-bind", "/dev/null", target, "--ro-bind", "/dev/null", originalTarget);
    }
  }
  return args;
}
