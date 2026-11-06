// バッチの終わり方の共通部品。実行係は終了コード(0=成功・1=一時的な失敗・2=再試行しても直らない失敗)と
// 標準出力の最終行(成功のときだけ DIGEST-BATCH-OK)で成否と失敗の種類を読み取る。

export const SUCCESS_MARKER = "DIGEST-BATCH-OK";
export const WARN_PREFIX = "DIGEST-BATCH-WARN";

/** 標準出力への書き出しと終了の差し替え口(テストでは偽物を渡す) */
export interface ExitIO {
  /** text を標準出力に書き、書き終わったら done を呼ぶ */
  write(text: string, done: () => void): void;
  exit(code: number): void;
}

export interface BatchExit {
  /** 完遂。最終行に成功マーカーを出して終了コード0で終わる */
  finishOk(): void;
  /** 一時的な失敗。理由を1行出して終了コード1で終わる */
  failTemporary(reason: string): void;
  /** 再試行しても直らない失敗(利用枠切れ・設定の誤り)。理由を1行出して終了コード2で終わる */
  failPermanent(reason: string): void;
  /** 警告の行を1行出す。終了しない。finishOk() の前に呼ぶ */
  warn(kind: string): void;
}

export function createExit(io: ExitIO): BatchExit {
  const finish = (line: string, code: number): void => {
    // 書き終わってから終了する(macOS ではパイプへの書き込みが非同期で、すぐ終了すると最終行が欠ける)
    io.write(`${line}\n`, () => io.exit(code));
  };
  return {
    finishOk: () => finish(SUCCESS_MARKER, 0),
    failTemporary: (reason) => finish(reason, 1),
    failPermanent: (reason) => finish(reason, 2),
    warn: (kind) => io.write(`${WARN_PREFIX} ${kind}\n`, () => {}),
  };
}

const nodeIO: ExitIO = {
  write(text, done) {
    process.stdout.write(text, done);
  },
  exit(code) {
    process.exit(code);
  },
};

const processExit = createExit(nodeIO);

export const finishOk = processExit.finishOk;
export const failTemporary = processExit.failTemporary;
export const failPermanent = processExit.failPermanent;
export const warn = processExit.warn;
