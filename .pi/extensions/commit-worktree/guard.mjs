const STATUS_ARGS = ["status", "--porcelain=v1", "--untracked-files=all"];

export const COMMIT_RULE = `【Git完了条件（必須）】このリポジトリでファイルを変更する作業は、関連テストと差分確認を行い、タスクに関係する変更だけを意味のあるメッセージでコミットし、git status --porcelain が空になって初めて完了です。未コミットの変更がある状態で最終回答を送ってはいけません。作業開始時から無関係な変更がある場合は、それを勝手に含めず、編集前に停止してユーザーへ報告してください。`;

export async function readGitStatus(exec) {
  const result = await exec("git", STATUS_ARGS);
  if (result.code !== 0) return { inRepo: false, status: "" };
  return { inRepo: true, status: result.stdout };
}

export function fallbackCommitMessage(prompt) {
  const summary = String(prompt || "")
    .replace(/[\u0000-\u001f\u007f]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/^\/+/, "")
    .slice(0, 68);
  return `chore(pi): ${summary || "complete requested changes"}`;
}

/**
 * Last-resort guard for a model that forgot to commit. It only stages all files
 * when the turn began clean, so pre-existing user work can never be swept into
 * an automatic commit.
 */
export async function ensureCommittedWorktree(exec, baselineStatus, prompt) {
  const current = await readGitStatus(exec);
  if (!current.inRepo) return { status: "not-git" };
  if (!current.status.trim()) return { status: "clean" };
  if (String(baselineStatus || "").trim()) {
    return { status: "preexisting-dirty", detail: current.status };
  }

  const add = await exec("git", ["add", "-A"]);
  if (add.code !== 0) {
    return { status: "failed", detail: add.stderr || add.stdout || "git add failed" };
  }

  const message = fallbackCommitMessage(prompt);
  const commit = await exec("git", ["commit", "-m", message]);
  if (commit.code !== 0) {
    return { status: "failed", detail: commit.stderr || commit.stdout || "git commit failed" };
  }

  const after = await readGitStatus(exec);
  if (!after.inRepo || after.status.trim()) {
    return { status: "failed", detail: after.status || "worktree is still dirty after commit" };
  }
  return { status: "committed", message };
}
