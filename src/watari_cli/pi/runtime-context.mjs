import { hostname as currentHostname } from "node:os";

function slug(value) {
  return String(value || "")
    .toLocaleLowerCase("und")
    .replace(/[^a-z0-9-]+/g, "-")
    .replace(/^-+|-+$/g, "") || "unknown";
}

function platformName(platform) {
  if (platform === "win32") return "windows";
  if (platform === "darwin") return "darwin";
  return platform || "unknown";
}

export function detectRuntimeContext(options = {}) {
  const platform = options.platform ?? process.platform;
  const env = options.env ?? process.env;
  const hostname = options.hostname ?? currentHostname();
  const cwd = options.cwd ?? process.cwd();
  const isWsl = platform === "linux" && Boolean(env.WSL_DISTRO_NAME || env.WSL_INTEROP);
  const computer = isWsl || platform === "win32"
    ? "windows"
    : platform === "darwin" ? "mac" : "linux";
  return {
    machine_id: slug(`${platformName(platform)}-${hostname}`),
    hostname,
    computer,
    runtime: isWsl ? "wsl" : "native",
    wsl_distribution: isWsl ? env.WSL_DISTRO_NAME || null : null,
    cwd,
  };
}
