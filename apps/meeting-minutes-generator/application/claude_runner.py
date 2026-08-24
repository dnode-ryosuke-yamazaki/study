"""claude -p(ヘッドレス)の起動と、生成結果の検証。

claude -p はMCPを使えず、**exit 0 でも失敗していることがある**(既知の制約)。
そのため終了コードだけを信用せず、生成結果が議事録として成立しているか
(必須見出しの存在)をここで検証し、通らなければ生成失敗として扱う。

見出し構成と要約の上限は会議ごとに変わるため、`meeting_profile.会議の性質` を
受け取り、**構成指示と検証が必ず同じ性質から導いた見出しを使う**ようにしている。

対応する仕様: design.md#議事録の生成 /
requirements.md#生成手段(claude -p)の制約への対処
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import meeting_profile

#: claudeコマンドの場所を明示指定する環境変数。検証時や、下の候補に無い場所へ
#: インストールしている場合に使う。
コマンド環境変数 = "MINUTES_GENERATOR_CLAUDE"

#: ヘッドレス実行を指示する引数。トランスクリプトは引数ではなく標準入力で渡す
#: (会議が長いと引数長の上限を超えるため)。
_ヘッドレス引数 = "-p"


def 既知の候補() -> tuple[Path, ...]:
    """claudeが置かれる代表的な場所。**launchd経由の実行では効く手段がこれだけ。**

    launchdはログインシェルのPATHを継承しないため、`claude` を名前で起動すると
    「見つからない」で全件失敗する。ここを探索することで、環境変数やシェルの
    設定に依存せずに起動できる(証明書バンドルを自分で探すteams-transcript-fetcher
    と同じ考え方)。
    """
    ホーム = Path.home()
    return (
        ホーム / ".local/bin/claude",
        ホーム / ".claude/local/claude",
        Path("/usr/local/bin/claude"),
        Path("/opt/homebrew/bin/claude"),
        ホーム / ".bun/bin/claude",
        ホーム / ".npm-global/bin/claude",
    )


def claudeコマンドを探す() -> str | None:
    """起動するclaudeの絶対パスを決める。見つからなければNoneを返す。

    優先順位は「環境変数での明示指定 → PATH → 既知の候補」。
    """
    指定された場所 = os.environ.get(コマンド環境変数)
    if 指定された場所:
        return 指定された場所

    PATHにある場所 = shutil.which("claude")
    if PATHにある場所:
        return PATHにある場所

    for 候補 in 既知の候補():
        if 候補.exists():
            return str(候補)

    return None


@dataclass(frozen=True)
class 生成の結果:
    成功: bool
    本文: str = ""
    #: 失敗理由の分類(ログ用)。タイムアウト / 終了コード非0 / 検証NG / 起動失敗
    失敗の分類: str = ""
    詳細: str = ""


def 構成指示を組み立てる(vtt名: str, 性質: meeting_profile.会議の性質) -> str:
    """議事録の構成と書き方のルールをclaude -pへの指示にする。

    対話での軌道修正が効かないため、承認済みのビジネスルールをすべてここに含める。
    見出しの並びと要約の上限は会議の性質から導いたものを使う。
    仕様: requirements.md#議事録の記載内容 [1]〜[8] /
    requirements.md#会議種別による構成の切り替え
    """
    見出しの並び = "、".join(性質.必須見出し)
    上限 = 性質.要約の上限
    進捗のルール = (
        (
            "- 「進捗」は担当者ごとに `### 担当者名` の小見出しを立て、その下に"
            "「- 作業実績: 」「- 作業予定: 」「- 課題: 」の3項目を1行ずつ書く"
            "(該当がない項目は「なし」と書く)\n"
            "- この会議は定期進捗確認のため、対応中タスクの進捗報告は「進捗」に書く。"
            "「決定事項」「TODO」には進捗報告以外(この会議で決まったこと・"
            "新たに発生したアクションアイテム)だけを書く\n"
        )
        if 性質.デイリー系
        else ""
    )
    return (
        "あなたは議事録の作成者です。標準入力で渡すTeams会議のトランスクリプト"
        "(WEBVTT)から、議事録をMarkdownで作成してください。\n"
        "\n"
        "構成のルール:\n"
        f"- 見出しは次の{len(性質.必須見出し)}つを、この順で `## 見出し名` として"
        f"必ずすべて立てる: {見出しの並び}\n"
        "- 決定事項・TODO・未決事項が1件もない場合も、見出しを省略せず本文に「なし」と書く\n"
        + 進捗のルール
        + "\n"
        "書き方のルール:\n"
        "- 議事録はトランスクリプトの言語によらず日本語で書く\n"
        f"- 「要約」は箇条書きで{上限.点数}以内、全体で{上限.字数}字以内に収める"
        "(1点は1行で簡潔に書く。読み手が要点だけを掴めることを優先し、"
        "詳細は「議論の経緯」に書く)\n"
        f"- 会議名・日時はトランスクリプトのファイル名「{vtt名}」と内容から判別できる範囲で書き、"
        "判別できない項目は「不明」と書く\n"
        "- 参加者一覧はトランスクリプトの発言者名から書き出す\n"
        "- TODOには発言者名・発言内容から推定した担当者候補を「(担当者候補: 名前)」の形で添え、"
        "推定できない場合は「(担当者未定)」と書く\n"
        "- 議事録本文だけを出力する(前置き・後書き・コードブロック囲みを付けない)\n"
    )


def 欠けている見出し(本文: str, 必須見出し: Sequence[str]) -> list[str]:
    """必須見出しのうち、Markdownの見出し行として存在しないものを返す。

    本文中に語として現れただけのもの(「決定事項は特にない」等)は見出しと
    数えない。検証する見出しは会議の性質から導いたものを受け取る
    (種別ごとに構成が違うため。仕様: requirements.md#会議種別による構成の切り替え [5])。
    仕様: requirements.md#生成手段(claude -p)の制約への対処 [1]
    """
    見出し行 = [
        行.lstrip("#").strip()
        for 行 in 本文.splitlines()
        if 行.lstrip().startswith("#")
    ]
    return [見出し for 見出し in 必須見出し if 見出し not in 見出し行]


def 生成する(
    トランスクリプト: str,
    vtt名: str,
    *,
    タイムアウト秒: int,
    性質: meeting_profile.会議の性質,
) -> 生成の結果:
    """claude -p で議事録を生成し、検証まで済ませた結果を返す。

    失敗はすべて`生成の結果`の分類として返す(例外にしない)。呼び出し元は分類を
    ログに残して再試行回数を進めるだけでよい。仕様: design.md#議事録の生成
    """
    コマンド = claudeコマンドを探す()
    if コマンド is None:
        return 生成の結果(
            成功=False,
            失敗の分類="起動失敗",
            詳細="claudeコマンドが見つからない(環境変数 "
            f"{コマンド環境変数} で場所を指定できる)",
        )

    指示 = 構成指示を組み立てる(vtt名, 性質)
    try:
        完了 = subprocess.run(
            [コマンド, _ヘッドレス引数, 指示],
            input=トランスクリプト,
            capture_output=True,
            text=True,
            timeout=タイムアウト秒,
        )
    except subprocess.TimeoutExpired:
        return 生成の結果(成功=False, 失敗の分類="タイムアウト", 詳細=f"{タイムアウト秒}秒")
    except (FileNotFoundError, OSError) as 例外:
        return 生成の結果(成功=False, 失敗の分類="起動失敗", 詳細=str(例外))

    if 完了.returncode != 0:
        # stderrは本文を含みうるため詳細には残さず、終了コードだけを返す。
        return 生成の結果(
            成功=False,
            失敗の分類="終了コード非0",
            詳細=f"exit={完了.returncode}",
        )

    本文 = 完了.stdout.strip()
    欠け = 欠けている見出し(本文, 性質.必須見出し)
    if 欠け:
        return 生成の結果(
            成功=False, 失敗の分類="検証NG", 詳細=f"欠けている見出し: {'、'.join(欠け)}"
        )

    return 生成の結果(成功=True, 本文=本文)
