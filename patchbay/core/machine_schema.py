"""machine.json の形(型・範囲・使える文字)。読み込み時と、画面からの保存の前に、検証する。

未知のキーは、警告(綴り間違いに気づくため)。型の誤りは、エラー(ハブは起動しない)。
サービス名・種別のキーは、ファイル名やフォルダ名に使うので、記号(/ や ..)を含まない形に限る。
"""
from .schema import Bool, DictOf, Int, ListOf, Num, Obj, Pair, Str

NAME = r"[A-Za-z0-9_-]+"                    # サービス名(<名前>.log などのファイル名に使う)
KEY = r"[A-Za-z0-9_-][A-Za-z0-9_.-]*"        # 種別のキー・フォルダ名(/ や .. を含まない)
ENVNAME = r"[A-Za-z_][A-Za-z0-9_]*"
FLAGNAME = r"-{1,2}[A-Za-z0-9][A-Za-z0-9-]*"
PATH = Str(1, 1000)

CATEGORY = Obj({"key": Str(1, 100, pattern=KEY), "dir": Str(1, 100, pattern=KEY), "label": Str(1, 100), "hint": Str(0, 300),
                "roles": ListOf(Str(1, 40)), "link": DictOf(Str(1, 100), key=Str(1, 40, pattern=NAME))}, required=["key", "label"])

FLAG = Obj({"flag": Str(1, 100, pattern=FLAGNAME), "aliases": ListOf(Str(1, 100, pattern=FLAGNAME)), "group": Str(0, 100),
            "short": Str(0, 200), "note": Str(0, 500)}, required=["flag"])

SERVICE = Obj({
    "label": Str(1, 100), "type": Str(enum=["llama", "script"]), "app": Str(1, 40, pattern=NAME), "group": Str(1, 40),
    "port": Int(1, 65535), "dir": PATH, "marker": Str(0, 300), "version_dir": PATH,
    "bin": Str(1, 300), "base_args": Str(0, 1000), "metrics": Bool(), "flags": ListOf(FLAG),
    "launcher": Obj({"venv": Str(1, 100), "script": Str(1, 300), "args": Str(0, 1000), "python": Str(0, 300),
                     "python_versions": ListOf(Str(1, 10)), "env": DictOf(Str(0, 1000), key=Str(1, 100, pattern=ENVNAME)),
                     "auto_venv": Bool()}),
    "scan": Str(1, 200), "api_key": Obj({"env": Str(1, 100, pattern=ENVNAME), "import_file": PATH}, required=["env"]),
    "models_dir": PATH, "exts": ListOf(Str(2, 20, pattern=r"\.[A-Za-z0-9]+")),
    "categories": ListOf(CATEGORY),
    "view": Obj({"dir": PATH, "yaml": PATH, "env": Str(1, 100, pattern=ENVNAME),
                 "saved_modules": Obj({"file": PATH, "key": Str(1, 100), "categories": ListOf(Str(1, 100, pattern=KEY))},
                                      required=["file", "key", "categories"])}, required=["dir"]),
    "dir_args": ListOf(Pair(Str(1, 100, pattern=FLAGNAME), Str(1, 100, pattern=KEY))),
    "refs_glob": Str(1, 200), "detect_names": ListOf(Str(1, 100)), "homepage": Str(0, 300, pattern=r"|https?://\S+"),
    "enabled": Bool(),
}, required=["label", "type", "dir", "models_dir"])

MACHINE = Obj({
    "host": Str(1, 255), "port": Int(1, 65535), "token": Str(0, 200, pattern=r"[\x21-\x7e]*"), "allow_private_downloads": Bool(), "allowed_hosts": ListOf(Str(1, 255)),
    "root": PATH, "apps_root": PATH, "models_root": PATH, "state_dir": PATH,
    "monitor": Obj({"interval_sec": Num(1, 3600), "history_hours": Num(0.01, 168)}),
    "hf_token": Str(0, 300), "civitai_token": Str(0, 300),
    "services": DictOf(SERVICE, key=Str(1, 40, pattern=NAME)),
}, required=["services"])
