import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Box, Text, hyperlink } from "@earendil-works/pi-tui";
import { buildFileLink, toolFileCandidate, validateLocalFile } from "./file-links.mjs";

type PendingFile = {
  path: string;
  actions: Set<string>;
};

type FileCardItem = {
  path: string;
  actions: string[];
  url: string;
};

type FileCardData = {
  files: FileCardItem[];
  omitted: number;
};

const ENTRY_TYPE = "watari-files";
const MAX_FILES = 20;

export default function (pi: ExtensionAPI) {
  const pending = new Map<string, PendingFile>();

  pi.registerEntryRenderer<FileCardData>(ENTRY_TYPE, (entry, _options, theme) => {
    const rawFiles = Array.isArray(entry.data?.files) ? entry.data.files : [];
    const rows: string[] = [];

    for (const item of rawFiles) {
      if (!item || typeof item.path !== "string" || typeof item.url !== "string") continue;
      try {
        const currentPath = validateLocalFile(item.path, process.cwd());
        const expectedUrl = buildFileLink(currentPath, process.cwd());
        if (expectedUrl !== item.url) continue;
        const labels = Array.isArray(item.actions)
          ? item.actions.filter((value): value is string => typeof value === "string").join("・")
          : "";
        rows.push(`  ${hyperlink(currentPath, expectedUrl)}${labels ? theme.fg("dim", `  ${labels}`) : ""}`);
      } catch {
        // 消滅・移動・権限変更されたファイルや、改ざんされたentryは表示しない。
      }
    }

    const box = new Box(1, 0, (text) => text);
    const hint = process.env.HERDR_ENV === "1" ? "Ctrl+クリックで開く" : "クリックで開く";
    box.addChild(new Text(`${theme.fg("accent", theme.bold("Files"))} ${theme.fg("dim", `— ${hint}`)}`, 0, 0));
    if (rows.length > 0) {
      box.addChild(new Text(rows.join("\n"), 0, 0));
    } else {
      box.addChild(new Text(theme.fg("dim", "  開けるファイルはありません"), 0, 0));
    }
    if (entry.data?.omitted) {
      box.addChild(new Text(theme.fg("dim", `  ほか ${entry.data.omitted} 件`), 0, 0));
    }
    return box;
  });

  pi.on("tool_result", (event, ctx) => {
    if (event.isError) return;
    const candidate = toolFileCandidate(event.toolName, event.input, ctx.cwd);
    if (!candidate) return;
    const existing = pending.get(candidate.path);
    if (existing) {
      existing.actions.add(candidate.action);
    } else {
      pending.set(candidate.path, { path: candidate.path, actions: new Set([candidate.action]) });
    }
  });

  pi.on("agent_settled", () => {
    if (pending.size === 0) return;
    const all = [...pending.values()].sort((left, right) => left.path.localeCompare(right.path));
    pending.clear();

    const files: FileCardItem[] = [];
    for (const file of all.slice(0, MAX_FILES)) {
      try {
        files.push({
          path: file.path,
          actions: [...file.actions],
          url: buildFileLink(file.path, process.cwd()),
        });
      } catch {
        // settledまでに消えたファイル、秘密ファイル、リンク等はカードへ載せない。
      }
    }
    if (files.length === 0) return;
    pi.appendEntry<FileCardData>(ENTRY_TYPE, {
      files,
      omitted: Math.max(0, all.length - MAX_FILES),
    });
  });
}
