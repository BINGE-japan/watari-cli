const STATUS_ARGS = ["status", "--porcelain=v1", "--untracked-files=all"];

export const COMMIT_RULE = `【Git完了条件（必須）】このリポジトリでファイルを変更する作業は、関連テストと差分確認を行い、タスクに関係する変更だけを意味のあるメッセージでコミットし、設定済みupstreamへpushし、git status --porcelainが空かつgit rev-list --left-right --count @{upstream}...HEADが0 0になって初めて完了です。ローカルcommitだけで最終回答を送ってはいけません。作業開始時から無関係な変更がある場合は、それを勝手に含めず、編集前に停止してユーザーへ報告してください。upstream未設定・push失敗・分岐時は自動で履歴を書き換えず、未完了として報告してください。`;

export async function readGitStatus(exec) {
  const result = await exec("git", STATUS_ARGS);
  if (result.code !== 0) return { inRepo: false, status: "" };
  return { inRepo: true, status: result.stdout };
}

export async function readGitHead(exec) {
  const result = await exec("git", ["rev-parse", "--verify", "HEAD"]);
  return result.code === 0 ? result.stdout.trim() : "";
}

export async function readUpstreamState(exec) {
  const upstreamResult = await exec(
    "git", ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"],
  );
  if (upstreamResult.code !== 0 || !upstreamResult.stdout.trim()) {
    return { status: "no-upstream", detail: upstreamResult.stderr || "branch has no upstream" };
  }
  const upstream = upstreamResult.stdout.trim();
  const count = await exec("git", ["rev-list", "--left-right", "--count", `${upstream}...HEAD`]);
  if (count.code !== 0) {
    return { status: "failed", detail: count.stderr || count.stdout || "cannot compare upstream" };
  }
  const match = count.stdout.trim().match(/^(\d+)\s+(\d+)$/);
  if (!match) return { status: "failed", detail: `unexpected rev-list output: ${count.stdout}` };
  return { status: "ok", upstream, behind: Number(match[1]), ahead: Number(match[2]) };
}

/**
 * Read-only completion check. Never commit or publish unvalidated changes.
 */
export async function ensurePublishedWorktree(exec, baselineStatus, baselineHead, _prompt) {
  const current = await readGitStatus(exec);
  if (!current.inRepo) return { status: "not-git" };
  if (String(baselineStatus || "").trim()) {
    return { status: "preexisting-dirty", detail: current.status || baselineStatus };
  }

  const currentHead = await readGitHead(exec);
  const hasWorktreeChanges = Boolean(current.status.trim());
  const hasNewCommit = Boolean(currentHead && currentHead !== String(baselineHead || "").trim());
  if (!hasWorktreeChanges && !hasNewCommit) return { status: "clean" };

  const upstream = await readUpstreamState(exec);
  if (upstream.status !== "ok") return upstream;
  if (upstream.behind > 0 && upstream.ahead > 0) {
    return { status: "diverged", detail: `${upstream.upstream} and HEAD have diverged` };
  }
  if (upstream.behind > 0) {
    return { status: "not-synchronized", detail: `HEAD is behind ${upstream.upstream}` };
  }
  if (hasWorktreeChanges) {
    return { status: "dirty", detail: "検証と差分レビューの後、対象の変更だけをコミットしてください。自動コミットは行いません。" };
  }
  if (upstream.ahead === 0) return { status: "published" };
  return { status: "not-synchronized", detail: "コミットが未公開です。検証後にgit pushを実行してください。" };
}
