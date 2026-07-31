const REDACTED = "<REDACTED_SECRET>";
const SECRET_KEYS = /^(?:api_key|access_token|refresh_token|token|authorization|client_secret|client_id|password|credential|cookie|private_key)$/i;
const TOKEN_PATTERNS = [
  /GOCSPX-[A-Za-z0-9_-]+/g,
  /gh[opusr]_[A-Za-z0-9]{20,}/g,
  /xox[pboa]-[A-Za-z0-9-]{20,}/g,
  /sk-[A-Za-z0-9_-]{20,}/g,
  /ya29\.[A-Za-z0-9._-]+/g,
  /Bearer\s+[A-Za-z0-9._-]{20,}/gi,
];

export function redactSensitiveText(value) {
  let text = String(value ?? "");
  for (const pattern of TOKEN_PATTERNS) text = text.replace(pattern, REDACTED);
  text = text.replace(
    /("(?:api_key|access_token|refresh_token|token|authorization|client_secret|client_id|password|credential|cookie|private_key)"\s*:\s*")([^"\\]+)(")/gi,
    `$1${REDACTED}$3`,
  );
  return text;
}

export function redactSensitiveValue(value, key = "") {
  if (SECRET_KEYS.test(key)) return REDACTED;
  if (typeof value === "string") return redactSensitiveText(value);
  if (Array.isArray(value)) return value.map((item) => redactSensitiveValue(item));
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value).map(([childKey, child]) => [childKey, redactSensitiveValue(child, childKey)]),
    );
  }
  return value;
}
