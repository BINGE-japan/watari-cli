const HOST_PATTERN = /^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$/;

export function parseAllowedHosts(raw = "") {
  const hosts = new Set();
  for (const item of String(raw).split(",")) {
    const host = item.trim().toLowerCase();
    if (HOST_PATTERN.test(host)) hosts.add(host);
  }
  return hosts;
}

export function assertLoopbackCdp(raw) {
  const url = new URL(String(raw || "http://127.0.0.1:9223"));
  const loopback = new Set(["127.0.0.1", "localhost", "[::1]"]);
  if (url.protocol !== "http:" || !loopback.has(url.hostname) || url.username || url.password) {
    throw new Error("Browser bridge must use an unauthenticated loopback HTTP endpoint");
  }
  return url.origin;
}

export function assertLoopbackWebSocket(raw) {
  const url = new URL(String(raw));
  const loopback = new Set(["127.0.0.1", "localhost", "[::1]"]);
  if ((url.protocol !== "ws:" && url.protocol !== "wss:") || !loopback.has(url.hostname) ||
      url.username || url.password) {
    throw new Error("Browser tab debugging endpoint must remain on loopback");
  }
  return url.href;
}

export function isAllowedPageUrl(raw, allowedHosts) {
  try {
    const url = new URL(String(raw));
    return url.protocol === "https:" && !url.username && !url.password &&
      allowedHosts.has(url.hostname.toLowerCase());
  } catch {
    return false;
  }
}

export function assertAllowedNavigation(raw, allowedHosts) {
  const url = new URL(String(raw));
  if (!isAllowedPageUrl(url.href, allowedHosts)) {
    throw new Error("Browser navigation is limited to explicitly allowed HTTPS hosts");
  }
  if (url.search || url.hash || url.pathname.length > 500 || /[\u0000-\u001f]/.test(url.pathname)) {
    throw new Error("Browser navigation cannot contain a query, fragment, control character, or oversized path");
  }
  return url.href;
}

export function sanitizePageUrl(raw) {
  try {
    const url = new URL(String(raw));
    if (url.protocol !== "https:" && url.protocol !== "http:") return "";
    return `${url.origin}${url.pathname}`;
  } catch {
    return "";
  }
}
