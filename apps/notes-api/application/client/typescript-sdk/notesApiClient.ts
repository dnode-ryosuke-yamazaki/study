/**
 * Notes API TypeScript Client Implementation
 *
 * このモジュールは、Notes APIに対するHTTPクライアントの実装を提供します。
 * OpenAPI 3.0.3仕様に基づいたNotes APIのエンドポイントをすべてサポートしています。
 */

// ============================================================================
// 型定義
// ============================================================================

/** メモオブジェクトの型定義 */
export type Note = {
  noteId: string;
  userId: string;
  title: string;
  content: string;
  tags?: string[];
  createdAt: string;
  updatedAt: string;
};

/** メモ一覧取得レスポンスの型定義 */
export type ListNotesResponse = {
  notes: Note[];
};

/** メモ作成リクエストの型定義 */
export type CreateNoteRequest = {
  title: string;
  content: string;
  tags?: string[];
};

/** メモ更新リクエストの型定義 */
export type UpdateNoteRequest = {
  title?: string;
  content?: string;
  tags?: string[];
};

/** APIエラーレスポンスボディの型定義 */
export type ApiErrorBody = {
  error: string;
  message: string;
  details?: Record<string, unknown>;
};

// ============================================================================
// 例外クラス
// ============================================================================

/**
 * APIエラーレスポンスを表現する例外クラス
 */
export class ApiError extends Error {
  statusCode: number;
  body?: ApiErrorBody;

  constructor(statusCode: number, message: string, body?: ApiErrorBody) {
    super(message);
    this.name = 'ApiError';
    this.statusCode = statusCode;
    this.body = body;
  }
}

// ============================================================================
// クライアント設定・初期化
// ============================================================================

/** NotesApiClientの初期化オプション */
export type NotesApiClientOptions = {
  baseUrl: string;
  defaultHeaders?: Record<string, string>;
};

// ============================================================================
// APIクライアントクラス
// ============================================================================

/**
 * Notes APIクライアント
 *
 * 使用例:
 * ```ts
 * const client = new NotesApiClient({
 *   baseUrl: "https://xxxxx.execute-api.ap-northeast-1.amazonaws.com/yamazaki-dev",
 * });
 *
 * const notes = await client.listNotes("user123");
 * ```
 */
export class NotesApiClient {
  private baseUrl: string;
  private defaultHeaders: Record<string, string>;

  /**
   * コンストラクタ
   *
   * @param options - クライアント初期化オプション
   */
  constructor(options: NotesApiClientOptions) {
    this.baseUrl = options.baseUrl.replace(/\/+$/, '');
    this.defaultHeaders = options.defaultHeaders ?? {};
  }

  /**
   * メモ一覧を取得する
   *
   * @param userId - ユーザーID
   * @returns ユーザーが所有するメモのリスト
   */
  async listNotes(userId: string): Promise<ListNotesResponse> {
    return this.request<ListNotesResponse>('GET', '/notes', {
      query: { userId },
    });
  }

  /**
   * 新規メモを作成する
   *
   * @param userId - ユーザーID
   * @param payload - メモ作成リクエスト
   * @returns 作成されたメモオブジェクト
   */
  async createNote(userId: string, payload: CreateNoteRequest): Promise<Note> {
    return this.request<Note>('POST', '/notes', {
      query: { userId },
      body: payload,
    });
  }

  /**
   * 指定されたIDのメモを取得する
   *
   * @param noteId - メモID
   * @returns メモオブジェクト
   */
  async getNote(noteId: string): Promise<Note> {
    return this.request<Note>('GET', `/notes/${encodeURIComponent(noteId)}`);
  }

  /**
   * 指定されたIDのメモを更新する
   *
   * @param noteId - メモID
   * @param payload - メモ更新リクエスト
   * @returns 更新されたメモオブジェクト
   * @throws Error - 更新内容が1つも指定されていない場合
   */
  async updateNote(noteId: string, payload: UpdateNoteRequest): Promise<Note> {
    if (!payload.title && !payload.content && !payload.tags) {
      throw new Error('At least one field is required for update');
    }

    return this.request<Note>('PUT', `/notes/${encodeURIComponent(noteId)}`, {
      body: payload,
    });
  }

  /**
   * 指定されたIDのメモを削除する
   *
   * @param noteId - メモID
   */
  async deleteNote(noteId: string): Promise<void> {
    await this.request<void>('DELETE', `/notes/${encodeURIComponent(noteId)}`, {
      expectedStatus: [204],
    });
  }

  /**
   * HTTPリクエストを実行する（プライベートメソッド）
   *
   * @template T - レスポンスボディの型
   * @param method - HTTPメソッド
   * @param path - APIパス
   * @param options - リクエストオプション
   * @returns APIレスポンスをJSON解析したオブジェクト
   * @throws ApiError - APIがエラーを返した場合
   */
  private async request<T>(
    method: string,
    path: string,
    options?: {
      query?: Record<string, string>;
      body?: unknown;
      expectedStatus?: number[];
    },
  ): Promise<T> {
    const expectedStatus = options?.expectedStatus ?? [200, 201];
    const url = new URL(`${this.baseUrl}${path}`);

    // クエリパラメータを URL に追加
    if (options?.query) {
      Object.entries(options.query).forEach(([key, value]) => {
        url.searchParams.set(key, value);
      });
    }

    const headers: Record<string, string> = {
      Accept: 'application/json',
      ...this.defaultHeaders,
    };

    // リクエストボディを JSON 形式でエンコード
    let body: string | undefined;
    if (options?.body !== undefined) {
      headers['Content-Type'] = 'application/json';
      body = JSON.stringify(options.body);
    }

    // fetch で HTTP リクエスト実行
    const response = await fetch(url.toString(), {
      method,
      headers,
      body,
    });

    // HTTP ステータスコードをチェック
    if (!expectedStatus.includes(response.status)) {
      await this.throwApiError(response);
    }

    // 204 No Content の場合は undefined を返す
    if (response.status === 204) {
      return undefined as T;
    }

    // レスポンスボディを JSON として解析
    const text = await response.text();
    if (!text) {
      return undefined as T;
    }

    return JSON.parse(text) as T;
  }

  /**
   * APIエラーレスポンスを例外に変換する（プライベートメソッド）
   *
   * @param response - HTTP レスポンスオブジェクト
   * @throws ApiError - 常に送出される
   */
  private async throwApiError(response: Response): Promise<never> {
    const text = await response.text();

    if (text) {
      try {
        const parsed = JSON.parse(text) as ApiErrorBody;
        throw new ApiError(response.status, `${parsed.error}: ${parsed.message}`, parsed);
      } catch {
        throw new ApiError(response.status, text);
      }
    }

    throw new ApiError(response.status, `HTTP ${response.status}`);
  }
}
