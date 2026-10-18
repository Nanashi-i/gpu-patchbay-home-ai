"""API のルート表(パス → (関数, 入力の形))。HTTP の細かいことは handler.py にあり、ここは「何を呼ぶか」と「入力の形」だけ。

関数は (query, body) を受け取る。query は、GET のクエリ(値は文字列)、body は、POST の JSON。
入力は、関数を呼ぶ前に、形(型・長さ・使える文字)を検証する(core/schema.py)。誤りは HubError(→ HTTP 400)。
戻り値が辞書ならそのまま JSON で返し、None なら {"ok": true} を返す。
"""
from ..apps import app_for
from ..apps._common import sets as model_sets
from ..core import secrets as secret_store
from ..core.config import ROOTS, service, services
from ..core.errors import HubError
from ..core.lifecycle import start_preset
from ..core.presets import delete_preset, upsert_preset
from ..core.process import stop_request
from ..core.schema import Bool, DictOf, Int, ListOf, Nullable, Obj, OneOf, Str
from ..core.services import resolve_path, update_service_config
from ..downloads import engine
from ..monitor import sampler
from .state import full_state

# ---------------------------------------------------------------- 入力の部品
NAME = r"[A-Za-z0-9_-]+"
SERVICE = Str(1, 40, pattern=NAME)
ID = Str(1, 64, pattern=r"[A-Za-z0-9_.-]+")
PATH = Str(1, 1000)
URL = Str(1, 2000, pattern=r"https?://\S+")
ANY_OBJ = Obj({}, extra="ignore")          # 中身は、関数(presets.clean など)が、アプリに合わせて検証する
FILES = DictOf(ListOf(Str(1, 500), 5000), key=Str(1, 100))


def _tail(path, n=200, max_bytes=512 * 1024):
    """ログの末尾 n 行。巨大なログでも、末尾の max_bytes だけを読む。"""
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - max_bytes))
            data = f.read()
    except FileNotFoundError:
        return ""
    return "".join(data.decode("utf-8", errors="replace").splitlines(keepends=True)[-n:])


# ---------------------------------------------------------------- GET
def _monitor(q, b):
    return sampler.SAMPLER.snapshot(float(q.get("since") or 0))


def _models(q, b):
    name = q.get("service", "llama")
    service(name)   # 不明なサービスは HubError
    return app_for(name).models(name)


def _resolve(q, b):
    return resolve_path(q.get("service", ""), q.get("path", ""), q.get("dir") == "1")


def _log(q, b):
    name = q.get("service", "")
    if name not in services():
        raise HubError("不明なサービス")
    return {"log": _tail(ROOTS.state / f"{name}.log")}


NO_QUERY = Obj({}, extra="ignore")
GET = {
    "/api/state": (lambda q, b: full_state(), NO_QUERY),
    "/api/monitor": (_monitor, Obj({"since": Str(0, 40, pattern=r"[0-9.]*")}, extra="ignore")),
    "/api/models": (_models, Obj({"service": SERVICE}, extra="ignore")),
    "/api/resolve": (_resolve, Obj({"service": SERVICE, "path": Str(0, 1000), "dir": Str(0, 1)}, extra="ignore")),
    "/api/log": (_log, Obj({"service": SERVICE}, extra="ignore")),
}

# ---------------------------------------------------------------- POST
POST = {
    "/api/start": (lambda q, b: start_preset(b.get("preset"), b.get("params"), b.get("label")),
                   Obj({"preset": Nullable(ID), "params": Nullable(ANY_OBJ), "label": Nullable(Str(0, 100))}, extra="ignore")),
    "/api/stop": (lambda q, b: stop_request(b.get("service")), Obj({"service": SERVICE}, required=["service"], extra="ignore")),
    "/api/preset": (lambda q, b: upsert_preset(b), ANY_OBJ),
    "/api/preset/delete": (lambda q, b: delete_preset(b.get("id")), Obj({"id": ID}, required=["id"], extra="ignore")),
    "/api/set": (lambda q, b: model_sets.upsert_set(b),
                 Obj({"id": Nullable(ID), "name": Str(1, 100), "note": Nullable(Str(0, 500)), "service": SERVICE, "files": Nullable(FILES)},
                     required=["name", "service"], extra="ignore")),
    "/api/set/delete": (lambda q, b: model_sets.delete_set(b.get("id")), Obj({"id": ID}, required=["id"], extra="ignore")),
    "/api/set/common": (lambda q, b: model_sets.set_common(b.get("service"), b.get("files")),
                        Obj({"service": SERVICE, "files": FILES}, required=["service", "files"], extra="ignore")),
    "/api/service/config": (lambda q, b: update_service_config(b.get("service"), b),
                            Obj({"service": SERVICE, "dir": PATH, "models_dir": PATH, "port": Int(1, 65535), "enabled": Bool()},
                                required=["service"], extra="ignore")),
    "/api/secret": (lambda q, b: secret_store.set_secret(b.get("service"), b),
                    Obj({"service": SERVICE, "key": Str(1, 500), "generate": Bool(), "import": Bool(), "clear": Bool()},
                        required=["service"], extra="ignore")),
    "/api/token": (lambda q, b: secret_store.set_token(b.get("kind"), b),
                   Obj({"kind": Str(enum=["hf", "civitai"]), "token": Str(0, 500), "clear": Bool()}, required=["kind"], extra="ignore")),
    "/api/dl/inspect": (lambda q, b: engine.inspect(b.get("url", "").strip(), b.get("service")),
                        Obj({"url": URL, "service": SERVICE}, required=["url", "service"], extra="ignore")),
    "/api/dl/start": (lambda q, b: engine.enqueue(b),
                      Obj({"service": SERVICE, "folder": Nullable(Str(0, 300)), "link": Bool(), "set_id": Nullable(Str(0, 64)),
                           "new_set": Nullable(Str(0, 100)), "repo": Nullable(Str(0, 200, pattern=r"|[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")),
                           "rev": Nullable(Str(0, 200)), "url": Nullable(Str(0, 2000, pattern=r"|https?://\S+")),
                           "files": ListOf(OneOf(Str(1, 500), Obj({"path": Str(0, 500), "category": Nullable(Str(0, 100))}, extra="ignore")), 500)},
                          required=["service", "files"], extra="ignore")),
    "/api/dl/cancel": (lambda q, b: engine.cancel(b.get("id")), Obj({"id": Str(1, 40)}, required=["id"], extra="ignore")),
    "/api/dl/clear": (lambda q, b: engine.clear_finished(), ANY_OBJ),
}
