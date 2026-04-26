/**
 * React での利用例
 *
 * このファイルは、Reactコンポーネント内でNotesApiClientを使用する方法のサンプルです。
 * 実際のReactプロジェクトでは、このファイルをベースにカスタマイズして使用してください。
 */

import { NotesApiClient } from "./notesApiClient";

// ============================================================================
// クライアント初期化
// ============================================================================

/**
 * APIクライアントを初期化
 * 注: terraform output の api_gateway_url は末尾 /notes 付きなので、
 *     ここでは環境名までを指定する
 */
const client = new NotesApiClient({
  baseUrl: "https://xxxxx.execute-api.ap-northeast-1.amazonaws.com/yamazaki-dev",
});

// ============================================================================
// 利用例：ヘルパー関数
// ============================================================================

/**
 * メモ一覧を読み込む
 *
 * @param userId - ユーザーID
 * @returns メモ配列
 */
export async function loadNotes(userId: string) {
  const response = await client.listNotes(userId);
  return response.notes;
}

/**
 * 新規メモを追加する
 *
 * @param userId - ユーザーID
 * @param title - メモのタイトル
 * @param content - メモの本文
 * @returns 作成されたメモオブジェクト
 */
export async function addNote(userId: string, title: string, content: string) {
  return client.createNote(userId, { title, content });
}
