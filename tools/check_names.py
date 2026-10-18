"""(開発用)未定義の名前と、未使用の import を探す、簡易チェック(pyflakes の代わり)。"""
import builtins
import symtable
import sys
from pathlib import Path


def walk(t):
    yield t
    for c in t.get_children():
        yield from walk(c)


def check(path):
    src = Path(path).read_text()
    top = symtable.symtable(src, str(path), "exec")
    mod_names = {s.get_name() for s in top.get_symbols() if s.is_assigned() or s.is_imported() or s.is_namespace()}
    referenced = {s.get_name() for s in top.get_symbols() if s.is_referenced()}
    problems = []
    for t in walk(top):
        for s in t.get_symbols():
            n = s.get_name()
            if t is top:
                if s.is_referenced() and n not in mod_names and not hasattr(builtins, n):
                    problems.append(f"未定義: {n}")
            elif s.is_global() and s.is_referenced():
                referenced.add(n)
                if n not in mod_names and not hasattr(builtins, n):
                    problems.append(f"未定義: {n} (in {t.get_name()})")
    exported = set()
    for s in top.get_symbols():
        if s.is_imported() and s.get_name() not in referenced and not path.endswith("__init__.py"):
            exported.add(s.get_name())
    problems += [f"未使用の import: {n}" for n in sorted(exported)]
    return problems


if __name__ == "__main__":
    bad = 0
    for p in sorted(Path(sys.argv[1]).rglob("*.py")):
        for msg in check(str(p)):
            print(f"{p}: {msg}")
            bad += 1
    print("問題なし" if not bad else f"{bad} 件")
