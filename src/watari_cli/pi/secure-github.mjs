import { realpathSync, statSync } from "node:fs";
import { isAbsolute } from "node:path";

const REPO_NAME = /^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$/;
const LOGIN = /^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$/;

export function assertGhExecutable(raw) {
  const candidate = String(raw || "");
  if (!candidate || !isAbsolute(candidate)) {
    throw new Error("Safe GitHub executable is not configured");
  }
  const resolved = realpathSync(candidate);
  const mode = statSync(resolved);
  if (!mode.isFile() || (mode.mode & 0o111) === 0) {
    throw new Error("Safe GitHub executable is unavailable");
  }
  return resolved;
}

export function normalizeRepoName(raw) {
  const name = String(raw || "").trim();
  if (!REPO_NAME.test(name) || name === "." || name === ".." || /\.git$/i.test(name)) {
    throw new Error("Repository name must be 1-100 safe characters and cannot end in .git");
  }
  return name;
}

export function normalizeLogin(raw) {
  const login = String(raw || "").trim();
  if (!LOGIN.test(login)) throw new Error("GitHub returned an invalid account name");
  return login;
}

export function normalizeVisibility(raw) {
  const visibility = String(raw || "private").trim().toLowerCase();
  if (visibility !== "private" && visibility !== "public") {
    throw new Error("Repository visibility must be private or public");
  }
  return visibility;
}

export function normalizeDescription(raw) {
  const description = String(raw || "").trim();
  if (description.length > 350 || /[\u0000-\u001f\u007f\u202a-\u202e\u2066-\u2069]/i.test(description)) {
    throw new Error("Repository description is invalid or too long");
  }
  return description;
}

export function identityArgs() {
  return ["api", "--hostname", "github.com", "user"];
}

export function repositoryArgs(login, name) {
  return ["api", "--hostname", "github.com", `repos/${normalizeLogin(login)}/${normalizeRepoName(name)}`];
}

export function createRepositoryArgs(name, visibility = "private", description = "") {
  const safeName = normalizeRepoName(name);
  const safeVisibility = normalizeVisibility(visibility);
  const safeDescription = normalizeDescription(description);
  return [
    "api", "--hostname", "github.com", "--method", "POST", "user/repos",
    "-f", `name=${safeName}`,
    "-f", `description=${safeDescription}`,
    "-F", `private=${safeVisibility === "private"}`,
  ];
}

export function deleteRepositoryArgs(login, name) {
  return [
    "api", "--hostname", "github.com", "--method", "DELETE",
    `repos/${normalizeLogin(login)}/${normalizeRepoName(name)}`,
  ];
}

export function safeRepositoryResult(value, expectedLogin) {
  if (!value || typeof value !== "object") throw new Error("GitHub returned an invalid repository");
  const login = normalizeLogin(expectedLogin);
  const fullName = String(value.full_name || "");
  const [owner, name, extra] = fullName.split("/");
  if (extra || owner.toLowerCase() !== login.toLowerCase()) {
    throw new Error("GitHub repository is outside the authenticated account");
  }
  const safeName = normalizeRepoName(name);
  const visibility = normalizeVisibility(value.visibility || (value.private ? "private" : "public"));
  const htmlUrl = String(value.html_url || "");
  const expectedUrl = `https://github.com/${owner}/${safeName}`;
  if (htmlUrl !== expectedUrl) throw new Error("GitHub returned an unexpected repository URL");
  return {
    fullName: `${owner}/${safeName}`,
    visibility,
    htmlUrl: expectedUrl,
    defaultBranch: String(value.default_branch || "").slice(0, 200),
  };
}
