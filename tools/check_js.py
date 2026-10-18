"""web/js の簡易チェック(ES モジュール用)。標準ライブラリだけ。使い方: python3 tools/check_js.py [web/js]

  - import した名前が、相手のファイルで export されているか
  - import したのに使っていない名前
  - 他のファイルの export と同じ名前を使っているのに、import していない(import 漏れ。ローカル変数の同名は、誤検出になる)
  - どこにも宣言も import もない名前の呼び出し(未定義の関数。置き換え漏れの検出)
  - import の循環(ファイル同士が、ぐるぐる参照していないか)
  - node があれば、構文の確認(node --check)
"""
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

JS = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "web" / "js")


def strip(s):
    """コメント・文字列・テンプレートの文章部分・正規表現を空にして、コードだけを残す(テンプレートの ${…} の中は、コードとして残す)。"""
    out, i, n = [], 0, len(s)
    stack = []   # テンプレートの ${ の中にいるときの、波かっこの深さ
    depth = 0
    last = ""    # 直前の、空白以外の文字(正規表現の判定用)

    def template(i):
        """テンプレートの文章を読み飛ばし、終わり(` か ${)の次の位置と、${ に入ったかを返す。"""
        while i < n:
            c = s[i]
            if c == "\\":
                i += 2
            elif c == "`":
                return i + 1, False
            elif c == "$" and s[i + 1:i + 2] == "{":
                return i + 2, True
            else:
                i += 1
        return i, False

    while i < n:
        c = s[i]
        if c == "/" and s[i + 1:i + 2] == "*":
            i = s.find("*/", i + 2)
            i = n if i < 0 else i + 2
        elif c == "/" and s[i + 1:i + 2] == "/":
            i = s.find("\n", i)
            i = n if i < 0 else i
        elif c in "'\"":
            j = i + 1
            while j < n and s[j] != c:
                j += 2 if s[j] == "\\" else 1
            out.append(c + c)
            i, last = j + 1, c
        elif c == "`":
            out.append("``")
            i, inside = template(i + 1)
            if inside:
                stack.append(depth)
                depth = 0
            last = "`"
        elif c == "/" and last in "(,=:[!&|?{};" + "":
            j = i + 1
            while j < n and s[j] != "/" and s[j] != "\n":
                j += 2 if s[j] == "\\" else (1 if s[j] != "[" else (s.find("]", j) - j + 1 or 1))
            out.append("//")
            i, last = j + 1, "/"
        else:
            if c == "{":
                depth += 1
            elif c == "}":
                if stack and depth == 0:
                    depth = stack.pop()
                    i, inside = template(i + 1)
                    if inside:
                        stack.append(depth)
                        depth = 0
                    out.append(" ")
                    continue
                depth -= 1
            out.append(c)
            if not c.isspace():
                last = c
            i += 1
    return "".join(out)


def names_in(spec):
    return [n.strip().split(" as ")[-1].strip() for n in spec.split(",") if n.strip()]


raw = {p.stem: p.read_text() for p in sorted(JS.glob("*.js"))}
files = {f: strip(t) for f, t in raw.items()}
exports, imports = {}, {}
for f, s in raw.items():
    ex = set()
    for m in re.finditer(r"^export\s+(?:async\s+)?(?:function\s+(\w+)|(?:const|let|var)\s+(\w+|\$))", s, re.M):
        ex.add(m.group(1) or m.group(2))
    for m in re.finditer(r"^export\s+(?:const|let|var)\s+[^;\n]*?,\s*(\w+)\s*=(?![>=])", s, re.M):
        ex.add(m.group(1))
    exports[f] = ex
    imports[f] = {}
    for m in re.finditer(r"^import\s*\{([^}]*)\}\s*from\s*'\./([\w-]+)\.js'", s, re.M):
        imports[f].setdefault(m.group(2), []).extend(names_in(m.group(1)))
    for m in re.finditer(r"^import\s*'\./([\w-]+)\.js'", s, re.M):
        imports[f].setdefault(m.group(1), [])


def used(f, n):
    body = re.sub(r"^import[^\n]*\n", "", files[f], flags=re.M)
    body = re.sub(r"[{,]\s*[\w$]+\s*:", " ", body)   # オブジェクトのキーは、使用ではない
    return re.search(r"(?<![\w$.])" + re.escape(n) + r"(?![\w$])", body) is not None


problems = []
all_exports = {n: f for f, ex in exports.items() for n in ex}
for f in files:
    imported = set()
    for src, names in imports[f].items():
        if src not in files:
            problems.append(f"{f}: ./{src}.js がありません")
            continue
        for n in names:
            imported.add(n)
            if n not in exports[src]:
                problems.append(f"{f}: {src}.js は {n} を export していません")
            elif not used(f, n):
                problems.append(f"{f}: {n} を import していますが、使っていません")
    for n, owner in all_exports.items():
        if owner != f and n not in imported and n not in exports[f] and used(f, n):
            if not re.search(r"(?:function\s+|const\s+|let\s+|var\s+)" + re.escape(n) + r"(?![\w$])", files[f]):
                problems.append(f"{f}: {n}({owner}.js)を使っていますが、import していません")
    for n in re.findall(r"^export\s+(?:async\s+)?(?:function\s+(\w+)|(?:const|let|var)\s+(\w+))", files[f], re.M):
        name = n[0] or n[1]
        if not any(name in imports[g].get(f, []) for g in files):
            problems.append(f"{f}: {name} を export していますが、どこからも import されていません")

# --- 未定義の関数の呼び出し
KEYWORDS = set("if for while switch catch function return typeof new await async do else try finally with super import delete void in of".split())
BUILTINS = set("""String Number Object Array JSON Math Set Map Date Promise parseInt parseFloat setTimeout setInterval clearTimeout
clearInterval alert confirm prompt fetch Error Boolean encodeURIComponent decodeURIComponent requestAnimationFrame Event isNaN isFinite
getComputedStyle Symbol RegExp URLSearchParams atob btoa Intl Uint8Array Float64Array structuredClone queueMicrotask""".split())


def declared_names(code):
    names = set(re.findall(r"\b(?:function\*?|const|let|var|class)\s+([\w$]+)", code))
    for m in re.finditer(r"\b(?:const|let|var)\s*[\[{]([^\]}]*)[\]}]", code):
        names |= set(re.findall(r"[\w$]+", m.group(1)))
    for m in re.finditer(r"(?:function\*?\s*[\w$]*|\bcatch)\s*\(([^)]*)\)|\(([^()]*)\)\s*=>", code):
        for part in (m.group(1) or m.group(2) or "").split(","):
            names |= set(re.findall(r"[\w$]+", part.split("=")[0]))
    names |= set(re.findall(r"([\w$]+)\s*=>", code))
    names |= set(re.findall(r",\s*([\w$]+)\s*=(?![=>])", code))   # const a=1, b=2 の、2つ目以降
    for m in re.finditer(r"\bfor\s*\(\s*(?:const|let|var)\s+(?:\[([^\]]*)\]|\{([^}]*)\}|([\w$]+))", code):
        names |= set(re.findall(r"[\w$]+", m.group(1) or m.group(2) or m.group(3) or ""))
    return names


for f, code in files.items():
    known = declared_names(code) | {n for ns in imports[f].values() for n in ns} | KEYWORDS | BUILTINS
    for n in sorted(set(re.findall(r"(?<![\w$.])([A-Za-z_$][\w$]*)\s*\(", code)) - known):
        problems.append(f"{f}: {n}() を呼んでいますが、宣言も import もありません")

# 循環
graph = {f: [s for s in imports[f] if s in files] for f in files}
state_, stack = {}, []


def visit(f):
    state_[f] = 1
    stack.append(f)
    for g in graph[f]:
        if state_.get(g) == 1:
            problems.append("import の循環: " + " → ".join(stack[stack.index(g):] + [g]))
        elif g not in state_:
            visit(g)
    stack.pop()
    state_[f] = 2


for f in files:
    if f not in state_:
        visit(f)

# 構文
node = shutil.which("node")
if node:
    with tempfile.TemporaryDirectory() as d:
        for p in JS.glob("*.js"):
            t = Path(d) / (p.stem + ".mjs")
            t.write_text(p.read_text())
            r = subprocess.run([node, "--check", str(t)], capture_output=True, text=True)
            if r.returncode:
                problems.append(f"{p.name}: 構文エラー: " + r.stderr.strip().splitlines()[-1][:160])

for p in problems:
    print(p)
print(f"{len(problems)} 件")
sys.exit(1 if problems else 0)
