/**
 * promptfoo拡張フック(beforeEach/afterEach)。
 *
 * 「承認済みの要件書がある」「3点セットが揃っている」といった前提を要求するテストケースの
 * ために、実行直前だけ evals/.tmp/<case> に使い捨ての作業ディレクトリを作り、そのケースに
 * 必要な fixture を実ファイルとして配置する。プロンプトに fixture の内容を埋め込む方式だと、
 * Skillが手順どおり実ファイルを Read して不整合に気づき、確認待ちで止まる(Skill本来の手順と
 * プロンプトの上書き指示が矛盾する)ため、実ファイルとして置く。
 *
 * 作業ディレクトリは空の git リポジトリとして初期化する。Claude Code の project 設定解決は
 * cwd から git ルートまで祖先を遡って CLAUDE.md を集めるため、ここで境界を作っておかないと
 * evals/ より上の意図しない CLAUDE.md(study の CLAUDE.md など)が読み込まれる。
 *
 * 検証対象のSkillは study の .claude に置いたプロジェクトSkillなので、実運用と同じ経路
 * (setting_sources の project)で読ませるために、作業ディレクトリの .claude/ へ skills・agents と
 * Skillが参照する文書・lib を写す。settings.json・hooks/ は写さない(評価に hook の注入を混ぜない)。
 * evals 自身も写さない(作業ディレクトリが evals/.tmp の下にあり、自分を入れ子にコピーしてしまう)。
 *
 * 社内標準テンプレート(add-skeleton/evals/libs/extensions/stage-fixtures.mjs)の方式を、
 * この構成向けに簡略化したもの。
 */

import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import { execFileSync } from "child_process";

const EVALS_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const CLAUDE_DIR = path.resolve(EVALS_ROOT, "..");
const HARNESS_ENTRIES = [
  "skills",
  "agents",
  "dev-flow.md",
  "test-policy.md",
  "jira-ticket-check.md",
  "quality-standards",
  "lib",
];

function resolveWorkDir(relWorkDir) {
  return path.resolve(EVALS_ROOT, relWorkDir);
}

function buildWorkDir(workDir) {
  fs.rmSync(workDir, { recursive: true, force: true });
  fs.mkdirSync(workDir, { recursive: true });
  execFileSync("git", ["init", "-q"], { cwd: workDir });
}

function stageHarness(workDir) {
  for (const entry of HARNESS_ENTRIES) {
    fs.cpSync(path.join(CLAUDE_DIR, entry), path.join(workDir, ".claude", entry), {
      recursive: true,
      filter: (src) => path.basename(src) !== "__pycache__",
    });
  }
}

function stageFixture(workDir, from, to) {
  const src = path.resolve(EVALS_ROOT, from);
  const dest = path.join(workDir, to);
  fs.mkdirSync(path.dirname(dest), { recursive: true });
  fs.copyFileSync(src, dest);
}

export default async function extensionHook(hookName, context) {
  const vars = context?.test?.vars;
  if (!vars?.workDir) return;
  const workDir = resolveWorkDir(vars.workDir);

  if (hookName === "beforeEach") {
    buildWorkDir(workDir);
    stageHarness(workDir);
    for (const { from, to } of vars.stage ?? []) {
      stageFixture(workDir, from, to);
    }
    return { test: context.test };
  }

  if (hookName === "afterEach") {
    fs.rmSync(workDir, { recursive: true, force: true });
  }
}
