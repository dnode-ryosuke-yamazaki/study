// 検証用の偽バッチ(batch-runner タスク16・21 の環境スモーク専用)。
// 環境スモークが終わったら登録表(launchd/apps.json)から smoke を外し、このファイルも消す。
//
// DIGEST_SMOKE_MODE で振る舞いを切り替える:
//   ok         Claude の呼び出し部品(claude.ts)で Claude を1回呼び、応答の本文を記事ファイルに書いて成功マーカーで終わる。
//              利用枠切れなら終了コード2、それ以外の失敗(打ち切りを含む)は終了コード1で終わる
//   no-marker  成功マーカーを出さずに終了コード0で終わる(実行係の成否の判定で「失敗」になる形)
//   exit1      理由を1行出して終了コード1で終わる(一時的な失敗)
//   fetch      固定の情報源1件を HTTPS で取り、CAバンドル(NODE_EXTRA_CA_CERTS)経由で取れたことを出して成功マーカーで終わる

import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { callClaude } from "./claude.ts";
import { failPermanent, failTemporary, finishOk } from "./exit.ts";

const env = process.env;
const mode = env.DIGEST_SMOKE_MODE ?? "ok";

/** 登録表の artifacts(out/smoke/{date}{edition}/article.json)に合わせて生成物を1つ書く。実行係は成否の判定で生成物の有無と更新時刻を見る */
function writeArtifact(text: string): void {
  const appRoot = dirname(dirname(fileURLToPath(import.meta.url)));
  const date = env.DIGEST_DATE ?? "no-date";
  const editionSuffix = env.DIGEST_EDITION ? `-${env.DIGEST_EDITION}` : "";
  const dir = join(appRoot, "out", "smoke", `${date}${editionSuffix}`);
  mkdirSync(dir, { recursive: true });
  const article = {
    app: "smoke",
    date,
    edition: env.DIGEST_EDITION || null,
    attempt: env.DIGEST_ATTEMPT ?? null,
    text,
    writtenAt: new Date().toISOString(),
  };
  writeFileSync(join(dir, "article.json"), `${JSON.stringify(article, null, 2)}\n`);
}

async function runOk(): Promise<void> {
  const result = await callClaude({
    prompt: env.DIGEST_SMOKE_PROMPT ?? "「こんにちは」とだけ答えてください。",
    materials: env.DIGEST_SMOKE_MATERIALS ?? "",
    name: "smoke",
  });
  if (result.ok) {
    writeArtifact(result.text);
    finishOk();
  } else if (result.kind === "quota") {
    failPermanent("smoke: Claude の利用枠切れ (quota)");
  } else {
    failTemporary(`smoke: Claude の呼び出しに失敗 (${result.kind})`);
  }
}

async function fetchFixedSource(): Promise<void> {
  const url = env.DIGEST_SMOKE_SOURCE_URL ?? "https://example.com/";
  const started = Date.now();
  const response = await fetch(url);
  const body = await response.text();
  process.stdout.write(
    `smoke: fetched ${url} status=${response.status} bytes=${body.length} ms=${Date.now() - started} ca=${env.NODE_EXTRA_CA_CERTS ?? "(unset)"}\n`,
  );
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
}

switch (mode) {
  case "ok": {
    runOk().catch((error: unknown) => failTemporary(`smoke: ${String(error)}`));
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
      (error: unknown) => failTemporary(`smoke: fetch failed: ${String(error)}`),
    );
    break;
  }
  default: {
    failTemporary(`smoke: unknown DIGEST_SMOKE_MODE "${mode}"`);
  }
}
