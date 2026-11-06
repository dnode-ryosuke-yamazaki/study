import { describe, expect, it } from "vitest";
import { createExit } from "../../batch/exit.ts";

// 標準出力と終了を偽物に差し替え、書いた行と終了コードを記録する
function fakeIO() {
  const lines: string[] = [];
  const codes: number[] = [];
  const io = {
    write(text: string, done: () => void) {
      lines.push(...text.split("\n").filter((line) => line !== ""));
      done();
    },
    exit(code: number) {
      codes.push(code);
    },
  };
  return { io, lines, codes };
}

describe("バッチの終わり方(実行係が終了コードと標準出力の最終行で成否と失敗の種類を読み取れるようにする)", () => {
  // 仕様: apps/digest-platform/specs/batch-runner/requirements.md#成否の判定-2
  // 否定確認: 成功マーカーの文字列を変えると落ちる / 終了コード0を1にすると落ちる
  it("バッチが最後まで完遂したときは、最終行に成功マーカーを出して終了コード0で終わる", () => {
    const { io, lines, codes } = fakeIO();
    createExit(io).finishOk();
    expect(lines.at(-1)).toBe("DIGEST-BATCH-OK");
    expect(codes).toEqual([0]);
  });

  // 仕様: apps/digest-platform/specs/batch-runner/requirements.md#成否の判定-4
  // 否定確認: 一時的な失敗の終了コードを2にすると落ちる
  it("一時的な失敗のときは、理由を最終行に1行出して終了コード1で終わり、成功マーカーは出さない", () => {
    const { io, lines, codes } = fakeIO();
    createExit(io).failTemporary("情報源がすべて取得できなかった");
    expect(lines).toEqual(["情報源がすべて取得できなかった"]);
    expect(codes).toEqual([1]);
  });

  // 仕様: apps/digest-platform/specs/batch-runner/requirements.md#成否の判定-4
  // 否定確認: 再試行しても直らない失敗の終了コードを1にすると落ちる
  it("再試行しても直らない失敗(利用枠切れなど)のときは、理由を最終行に1行出して終了コード2で終わり、成功マーカーは出さない", () => {
    const { io, lines, codes } = fakeIO();
    createExit(io).failPermanent("Claude の利用枠が切れた");
    expect(lines).toEqual(["Claude の利用枠が切れた"]);
    expect(codes).toEqual([2]);
  });

  // 仕様: apps/digest-platform/specs/batch-runner/requirements.md#成否の判定-8
  // 否定確認: 警告の行を出したあとに終了するように変えると落ちる / 警告の接頭辞を変えると落ちる
  it("完遂したが新着の送り出しに失敗したときは、警告の行のあとに成功マーカーが最終行として出て、警告では終了しない", () => {
    const { io, lines, codes } = fakeIO();
    const ending = createExit(io);
    ending.warn("broadcast_failed");
    expect(codes).toEqual([]);
    ending.finishOk();
    expect(lines).toEqual(["DIGEST-BATCH-WARN broadcast_failed", "DIGEST-BATCH-OK"]);
    expect(codes).toEqual([0]);
  });
});
