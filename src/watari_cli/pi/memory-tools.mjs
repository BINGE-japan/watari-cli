import { spawn, execFile } from "node:child_process";
import { isAbsolute } from "node:path";

// Only the launcher's Python and one bundled module; never caller-supplied code.
export function runMemoryOperation(request, { signal, env = process.env, timeout = 60_000 } = {}) {
  const python = env.WATARI_PYTHON;
  if (!python || !isAbsolute(python) || !env.WATARI_HOME || !isAbsolute(env.WATARI_HOME)) {
    throw new Error("記憶の実行環境が未設定です。watari chatから起動してください。");
  }
  const payload = JSON.stringify({ ...request, version: 1 });
  if (Buffer.byteLength(payload) > 256_000) throw new Error("記憶の入力が上限を超えています。");
  signal?.throwIfAborted();
  return new Promise((resolve, reject) => {
    const child = spawn(python, ["-I", "-m", "watari_cli.memory_operations"], {
      env, shell: false, stdio: ["pipe", "pipe", "pipe"], windowsHide: true,
      detached: process.platform !== "win32",
    });
    let output = [], errors = [], size = 0, failure;
    const stop = (reason) => {
      if (failure) return;
      failure = reason;
      // Git may be a child of the fixed Python operation. Stop only our own tree,
      // not just the lock-holding parent while leaving its writes running.
      if (process.platform === "win32" && child.pid) {
        execFile("taskkill.exe", ["/PID", String(child.pid), "/T", "/F"], { windowsHide: true, timeout: 5000 },
          () => child.kill("SIGKILL"));
      } else {
        try { process.kill(-child.pid, "SIGKILL"); } catch { child.kill("SIGKILL"); }
      }
    };
    const abort = () => stop(new Error("処理を中断しました。保存済みの可能性があるため、同じ内容で結果を再確認してください。"));
    const timer = setTimeout(() => stop(new Error("記憶の処理が制限時間を超えました。保存結果は未確認です。")), timeout);
    const finish = () => { clearTimeout(timer); signal?.removeEventListener("abort", abort); };
    signal?.addEventListener("abort", abort, { once: true });
    if (signal?.aborted) abort();
    const collect = target => chunk => {
      size += chunk.length;
      if (size > 64_000) stop(new Error("記憶の応答が上限を超えました。保存結果は未確認です。"));
      else target.push(chunk);
    };
    child.stdout.on("data", collect(output));
    child.stderr.on("data", collect(errors));
    child.on("error", error => { finish(); reject(error); });
    child.on("close", code => {
      finish();
      if (failure) return reject(failure);
      try {
        const result = JSON.parse(Buffer.concat(output).toString("utf8"));
        if (code !== 0 || result.error) throw new Error(result.error || "記憶の処理に失敗しました。");
        const warning = Buffer.concat(errors).toString("utf8").trim();
        resolve(warning ? { ...result, operation_warning: warning } : result);
      } catch (error) { reject(error); }
    });
    child.stdin.on("error", () => {}); // EPIPE follows child exit; close handles its result.
    child.stdin.end(payload);
  });
}
