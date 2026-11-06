// @ts-nocheck
// 検証用の偽バッチ(batch-runner タスク16・21 の環境スモーク専用)。
// 環境スモークが終わったら登録表(launchd/apps.json)から smoke を外し、このファイルも消す。
// @types/node を入れるまで node: モジュールの型が無いため、このファイルだけ型検査を外している。
//
// DIGEST_SMOKE_MODE で振る舞いを切り替える:
//   ok         claude -p を appendix「Claude の呼び出し」の起動引数で1回呼び、封筒をそのまま標準出力に出して成功マーカーで終わる
//   no-marker  成功マーカーを出さずに終了コード0で終わる(実行係の成否の判定で「失敗」になる形)
//   exit1      理由を1行出して終了コード1で終わる(一時的な失敗)
//   fetch      固定の情報源1件を HTTPS で取り、CAバンドル(NODE_EXTRA_CA_CERTS)経由で取れたことを出して成功マーカーで終わる

import { spawnSync } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { finishOk, failTemporary } from "./exit.ts";

const mode = process.env.DIGEST_SMOKE_MODE ?? "ok";
const claudeBin = process.env.DIGEST_CLAUDE_BIN ?? "claude";
const prompt =
  process.env.DIGEST_SMOKE_PROMPT ??
  "「こんにちは」とだけ答えてください。最後の行に CLAUDE-CALL-OK だけを出力してください。";
const materials = process.env.DIGEST_SMOKE_MATERIALS ?? "";

function callClaudeOnce(): number | null {
  const args = [
    "-p",
    prompt,
    "--output-format",
    "json",
    "--tools",
    "WebSearch,WebFetch",
    "--disallowedTools",
    "mcp__*",
    "--permission-prompts",
    "none",
  ];
  const env = { ...process.env };
  delete env.ANTHROPIC_API_KEY;
  const result = spawnSync(claudeBin, args, {
    encoding: "utf8",
    env,
    input: materials,
    maxBuffer: 50 * 1024 * 1024,
    timeout: 10 * 60 * 1000,
  });
  if (result.error) {
    process.stderr.write(`smoke: claude を起動できない: ${String(result.error)}\n`);
    return null;
  }
  // 封筒をそのまま出す(最終行の改行は揃える)
  process.stdout.write(result.stdout.endsWith("\n") ? result.stdout : `${result.stdout}\n`);
  if (result.stderr) process.stderr.write(result.stderr);
  return result.status;
}

/** 登録表の artifacts(out/smoke/{date}{edition}/article.json)に合わせて生成物を1つ書く。実行係は成否の判定で生成物の有無と更新時刻を見る */
function writeArtifact(): void {
  const appRoot = dirname(dirname(fileURLToPath(import.meta.url)));
  const date = process.env.DIGEST_DATE ?? "no-date";
  const editionSuffix = process.env.DIGEST_EDITION ? `-${process.env.DIGEST_EDITION}` : "";
  const dir = join(appRoot, "out", "smoke", `${date}${editionSuffix}`);
  mkdirSync(dir, { recursive: true });
  const article = {
    app: "smoke",
    date,
    edition: process.env.DIGEST_EDITION || null,
    attempt: process.env.DIGEST_ATTEMPT ?? null,
    writtenAt: new Date().toISOString(),
  };
  writeFileSync(join(dir, "article.json"), `${JSON.stringify(article, null, 2)}\n`);
}

async function fetchFixedSource(): Promise<void> {
  const url = process.env.DIGEST_SMOKE_SOURCE_URL ?? "https://example.com/";
  const started = Date.now();
  const response = await fetch(url);
  const body = await response.text();
  process.stdout.write(
    `smoke: fetched ${url} status=${response.status} bytes=${body.length} ms=${Date.now() - started} ca=${process.env.NODE_EXTRA_CA_CERTS ?? "(unset)"}\n`,
  );
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
}

switch (mode) {
  case "ok": {
    const status = callClaudeOnce();
    if (status === 0) {
      writeArtifact();
      finishOk();
    } else {
      failTemporary(`smoke: claude の終了コード ${status ?? "起動失敗"}`);
    }
    break;
  }
  case "no-marker": {
    process.stdout.write("smoke: finished without the success marker\n", () => process.exit(0));
    break;
  }
  case "exit1": {
    failTemporary("smoke: intentional temporary failure (DIGEST_SMOKE_MODE=exit1)");
    break;
  }
  case "fetch": {
    fetchFixedSource().then(
      () => finishOk(),
      (error) => failTemporary(`smoke: fetch failed: ${String(error)}`),
    );
    break;
  }
  default: {
    failTemporary(`smoke: unknown DIGEST_SMOKE_MODE "${mode}"`);
  }
}
