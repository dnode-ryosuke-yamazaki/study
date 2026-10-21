"""Claude の応答から JSON を取り出す部品と、検査を通らなかったことを表す例外(appendix.md「Claude の応答の形」)"""

import json


class ResponseError(ValueError):
    """応答が検査を通らない。失敗の1回として数える。reason はログに書く短い分類"""

    def __init__(self, reason, message=""):
        super().__init__(message or reason)
        self.reason = reason


def parse_json_object(text):
    """応答の本文の最初の { から最後の } までを JSON のオブジェクトとして読む"""
    begin, end = text.find("{"), text.rfind("}")
    if begin < 0 or end < begin:
        raise ResponseError("invalidJson", "応答に JSON のオブジェクトがありません")
    try:
        parsed = json.loads(text[begin:end + 1])
    except ValueError:
        raise ResponseError("invalidJson", "応答を JSON として読めません") from None
    if not isinstance(parsed, dict):
        raise ResponseError("invalidJson", "応答が JSON のオブジェクトではありません")
    return parsed


def require(condition, message):
    """形の検査。合わなければ失敗の1回にする"""
    if not condition:
        raise ResponseError("invalidShape", message)
