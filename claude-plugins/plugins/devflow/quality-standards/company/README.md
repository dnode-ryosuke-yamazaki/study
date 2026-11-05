# company層(会社標準)

会社・組織全体で追加したいレビュー観点を、工程名と同じファイル名(`spec-review.md`・`implementation-review.md`)で置く。置いた時点で全プロジェクトのレビューに自動的に反映される(既存Skill・Agentの変更は不要)。

現在の中身は、社内のAI駆動開発 標準テンプレート(`add-skeleton`)の規約(`.claude/rules/coding-standards.md`・`development-process.md`・`documentation.md` と各スキルの手順)から、**成果物の書式に依存しない観点だけ**を抜き出したもの。書式に依存する規約(フロントマター必須項目・REQ/NFR/DSN/SPEC採番・必須見出しの固定・「対象外」の明記)は全プロジェクトに加算すると個人プロジェクトのspecが全件レビューに落ちるため、ここには置かず、標準テンプレートを採用したリポジトリ側の `.claude/quality-standards/`(project層)に置く。

標準テンプレート側の規約が更新されたら、同じ基準で抜き出し直す。書き方・合成ルールは[../README.md](../README.md)を参照。
