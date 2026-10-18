"""入力の検証(型・範囲・形)。依存のない、小さな検証器。

使う場所: 設定ファイル(machine.json)の読み込み、API の入力、プリセットの項目。
目的: 型の誤りや、想定外の入力(制御文字・巨大な値・文字列ではない値など)が、そのまま起動コマンドや
ファイルのパスに入り込まないようにする(ハブは、設定されたコマンドを実行するツールなので)。

  check(spec, value) -> (エラーの一覧, 警告の一覧)
  require(spec, value, what) -> エラーがあれば、すべてをまとめて HubError にする

  Str / Int / Num / Bool / ListOf / DictOf / Obj / Nullable / Any が、部品。
  文字列は、既定で、制御文字(NUL・改行など)を拒否する。
"""
import math
import re

from .errors import HubError


class Spec:
    def check(self, value, path, errors, warnings):
        raise NotImplementedError


def _label(path):
    return path or "(全体)"


class Str(Spec):
    def __init__(self, min=0, max=2000, pattern=None, enum=None, multiline=False):
        self.min, self.max, self.pattern, self.enum, self.multiline = min, max, pattern, enum, multiline

    def check(self, value, path, errors, warnings):
        if not isinstance(value, str):
            return errors.append(f"{_label(path)}: 文字列が必要です(いまは {type(value).__name__})")
        if not self.min <= len(value) <= self.max:
            return errors.append(f"{_label(path)}: 長さは {self.min}〜{self.max} 文字にしてください(いまは {len(value)})")
        if any(ord(c) < 32 or ord(c) == 127 for c in value if not (self.multiline and c == "\n")):
            return errors.append(f"{_label(path)}: 制御文字(改行・NULなど)は使えません")
        if self.enum is not None and value not in self.enum:
            return errors.append(f"{_label(path)}: {' / '.join(map(str, self.enum))} のどれかにしてください(いまは {value!r})")
        if self.pattern and not re.fullmatch(self.pattern, value):
            errors.append(f"{_label(path)}: 形式が正しくありません({value!r})")


class Int(Spec):
    def __init__(self, min=None, max=None):
        self.min, self.max = min, max

    def check(self, value, path, errors, warnings):
        if isinstance(value, bool) or not isinstance(value, int):
            return errors.append(f"{_label(path)}: 整数が必要です(いまは {value!r})")
        if (self.min is not None and value < self.min) or (self.max is not None and value > self.max):
            errors.append(f"{_label(path)}: {self.min}〜{self.max} の範囲にしてください(いまは {value})")


class Num(Spec):
    def __init__(self, min=None, max=None):
        self.min, self.max = min, max

    def check(self, value, path, errors, warnings):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or (isinstance(value, float) and not math.isfinite(value)):
            return errors.append(f"{_label(path)}: 数値が必要です(いまは {value!r})")
        if (self.min is not None and value < self.min) or (self.max is not None and value > self.max):
            errors.append(f"{_label(path)}: {self.min}〜{self.max} の範囲にしてください(いまは {value})")


class Bool(Spec):
    def check(self, value, path, errors, warnings):
        if not isinstance(value, bool):
            errors.append(f"{_label(path)}: true / false が必要です(いまは {value!r})")


class Any(Spec):
    def check(self, value, path, errors, warnings):
        pass


class OneOf(Spec):
    """いくつかの形の、どれか1つに合えばよい(例: 整数でも、文字列でもよい項目)。"""
    def __init__(self, *specs):
        self.specs = specs

    def check(self, value, path, errors, warnings):
        for sp in self.specs:
            e, w = [], []
            sp.check(value, path, e, w)
            if not e:
                return
        errors.append(f"{_label(path)}: 値の形が正しくありません({value!r})")


class Nullable(Spec):
    def __init__(self, spec):
        self.spec = spec

    def check(self, value, path, errors, warnings):
        if value is not None:
            self.spec.check(value, path, errors, warnings)


class ListOf(Spec):
    def __init__(self, item, max_items=1000):
        self.item, self.max_items = item, max_items

    def check(self, value, path, errors, warnings):
        if not isinstance(value, list):
            return errors.append(f"{_label(path)}: 配列が必要です(いまは {type(value).__name__})")
        if len(value) > self.max_items:
            return errors.append(f"{_label(path)}: 要素が多すぎます(最大 {self.max_items})")
        for i, v in enumerate(value):
            self.item.check(v, f"{path}[{i}]", errors, warnings)


class Pair(Spec):
    """決まった長さの配列。例: Pair(Str(), Str()) は [文字列, 文字列]。"""
    def __init__(self, *items):
        self.items = items

    def check(self, value, path, errors, warnings):
        if not isinstance(value, list) or len(value) != len(self.items):
            return errors.append(f"{_label(path)}: {len(self.items)} 個の配列が必要です")
        for i, (spec, v) in enumerate(zip(self.items, value)):
            spec.check(v, f"{path}[{i}]", errors, warnings)


class DictOf(Spec):
    def __init__(self, value, key=None, max_items=1000):
        self.value, self.key, self.max_items = value, key or Str(1, 200), max_items

    def check(self, value, path, errors, warnings):
        if not isinstance(value, dict):
            return errors.append(f"{_label(path)}: オブジェクトが必要です(いまは {type(value).__name__})")
        if len(value) > self.max_items:
            return errors.append(f"{_label(path)}: 要素が多すぎます(最大 {self.max_items})")
        for k, v in value.items():
            self.key.check(k, f"{path}.{k}(キー)", errors, warnings)
            self.value.check(v, f"{path}.{k}" if path else str(k), errors, warnings)


class Obj(Spec):
    """決まったキーを持つオブジェクト。未知のキーは、extra で扱いを決める(warn: 警告 / error: エラー / ignore: 無視)。"""
    def __init__(self, fields, required=(), extra="warn"):
        self.fields, self.required, self.extra = fields, set(required), extra

    def check(self, value, path, errors, warnings):
        if not isinstance(value, dict):
            return errors.append(f"{_label(path)}: オブジェクトが必要です(いまは {type(value).__name__})")
        for k in self.required:
            if k not in value:
                errors.append(f"{_join(path, k)}: 必須の項目がありません")
        for k, v in value.items():
            if k in self.fields:
                self.fields[k].check(v, _join(path, k), errors, warnings)
            elif self.extra == "warn":
                warnings.append(f"{_join(path, k)}: 未知のキーです(綴り間違いかもしれません)")
            elif self.extra == "error":
                errors.append(f"{_join(path, k)}: 未知のキーです")


def _join(path, key):
    return f"{path}.{key}" if path else str(key)


def check(spec, value, path=""):
    errors, warnings = [], []
    spec.check(value, path, errors, warnings)
    return errors, warnings


def require(spec, value, what="入力"):
    """エラーがあれば、すべてをまとめて HubError にする。警告は、戻り値で返す。"""
    errors, warnings = check(spec, value)
    if errors:
        shown = errors[:8] + ([f"…ほか {len(errors) - 8} 件"] if len(errors) > 8 else [])
        raise HubError(f"{what}に誤りがあります: " + " / ".join(shown))
    return warnings
