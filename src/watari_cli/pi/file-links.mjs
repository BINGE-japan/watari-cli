import { createHmac } from "node:crypto";
import {
  lstatSync,
  readFileSync,
  realpathSync,
  statSync,
} from "node:fs";
import { homedir, tmpdir } from "node:os";
import path from "node:path";

const SENSITIVE_SUFFIXES = new Set([".pem", ".key", ".p12", ".pfx", ".jks", ".keystore"]);
const SENSITIVE_TOKEN = /(?:^|[-_.])(secret|secrets|credential|credentials|token|tokens|password|passwd|api[-_]?key|private[-_]?key)(?:$|[-_.])/i;
const VERSION = "v1";

function hasControl(value) {
  return [...value].some((character) => character.codePointAt(0) < 32);
}

function hasSymlinkComponent(filePath) {
  const parsed = path.parse(filePath);
  let current = parsed.root;
  for (const part of filePath.slice(parsed.root.length).split(path.sep).filter(Boolean)) {
    current = path.join(current, part);
    if (lstatSync(current).isSymbolicLink()) return true;
  }
  return false;
}

function isSensitive(filePath) {
  const parsed = path.parse(filePath);
  const components = filePath
    .slice(parsed.root.length)
    .split(path.sep)
    .filter(Boolean);
  if (components.some((component) => component.startsWith("."))) return true;
  const basename = path.basename(filePath).toLowerCase();
  if (SENSITIVE_SUFFIXES.has(path.extname(basename)) || SENSITIVE_TOKEN.test(basename)) return true;
  const lowered = `/${components.map((part) => part.toLowerCase()).join("/")}/`;
  return ["/user data/", "/browser-profile/", "/browser_profile/", "/chrome-win/"]
    .some((marker) => lowered.includes(marker));
}

function isInside(filePath, root) {
  const relative = path.relative(root, filePath);
  return relative === "" || (!relative.startsWith(`..${path.sep}`) && relative !== "..");
}

export function validateLocalFile(rawPath, cwd = process.cwd()) {
  if (typeof rawPath !== "string" || rawPath.length === 0 || hasControl(rawPath)) {
    throw new Error("invalid file path");
  }
  const absolute = path.resolve(cwd, rawPath);
  const resolved = realpathSync.native(absolute);
  if (absolute !== resolved || hasSymlinkComponent(absolute)) {
    throw new Error("symlinked paths are not linkable");
  }
  const info = statSync(resolved);
  if (!info.isFile() || info.nlink !== 1) {
    throw new Error("only regular, non-hardlinked files are linkable");
  }
  if (typeof process.getuid === "function" && info.uid !== process.getuid()) {
    throw new Error("file owner does not match the current user");
  }
  if (isSensitive(resolved)) throw new Error("sensitive paths are not linkable");

  const roots = [homedir(), tmpdir(), path.resolve(cwd)];
  if (process.platform === "linux") roots.push("/mnt/c/Users");
  const allowed = roots
    .map((root) => {
      try { return realpathSync.native(root); } catch { return null; }
    })
    .filter(Boolean)
    .some((root) => isInside(resolved, root));
  if (!allowed) throw new Error("file is outside allowed roots");
  return resolved;
}

function loadKey(keyPath = process.env.WATARI_FILE_LINK_KEY_PATH) {
  if (!keyPath) throw new Error("file link key is not configured");
  const info = statSync(keyPath);
  if (!info.isFile() || (info.mode & 0o077) !== 0) {
    throw new Error("file link key must be an owner-only regular file");
  }
  if (typeof process.getuid === "function" && info.uid !== process.getuid()) {
    throw new Error("file link key owner does not match the current user");
  }
  const key = readFileSync(keyPath);
  if (key.length !== 32) throw new Error("file link key must contain exactly 32 bytes");
  return key;
}

export function buildFileLink(rawPath, cwd = process.cwd(), keyPath) {
  const filePath = validateLocalFile(rawPath, cwd);
  const payload = Buffer.from(filePath, "utf8").toString("base64url");
  const signature = createHmac("sha256", loadKey(keyPath))
    .update(`${VERSION}\0${filePath}`, "utf8")
    .digest("hex");
  return `watari-file://open/${payload}?sig=${signature}`;
}

export function toolFileCandidate(toolName, input, cwd = process.cwd()) {
  const labels = { read: "参照", edit: "更新", write: "保存" };
  const label = labels[toolName];
  if (!label || !input || typeof input.path !== "string") return null;
  try {
    return { path: validateLocalFile(input.path, cwd), action: label };
  } catch {
    return null;
  }
}
