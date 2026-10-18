"""/api/state: 画面が2秒ごとに読む、全体の状態の組み立て。"""
import glob
import os

from ..apps import app_for, app_id_of
from ..core.config import ROOTS, cat_meta, models_dir, service, services, to_path
from ..core.presets import load_presets
from ..core.process import OPS, service_status
from ..core.secrets import TOKENS, load_secrets, secrets_file, token_source
from ..core.services import detect_candidates, is_installed
from ..apps._common.sets import load_sets
from ..downloads import engine


def _abs_cmd(p):
    c = to_path(p.get("cmd", ""), p["service"])
    return str(c if c.is_absolute() else to_path(service(p["service"])["dir"]) / c)


def service_state(name, presets, known_cmds):
    svc, app = service(name), app_for(name)
    s = {"label": svc["label"], "type": svc["type"], "app": app_id_of(name), "port": svc.get("port"), "group": svc.get("group"),
         "models_dir": str(models_dir(name)), "categories": cat_meta(name), "view": bool(svc.get("view")),
         "launcher": bool(svc.get("launcher"))}
    s.update(app.extra_state(name))
    s.update(service_status(name))
    cur = next((p for p in presets if p["id"] == s.get("preset")), None) if s.get("state") != "stopped" else None
    s["version"] = app.version(name, cur)
    if svc.get("api_key"):
        s["key"] = "set" if load_secrets().get(name) else "needed"
        imp = svc["api_key"].get("import_file")
        s["key_import"] = to_path(imp).is_file() if imp else False
        s["secrets_file"] = str(secrets_file())
    s["enabled"] = svc.get("enabled", True)
    s["installed"] = is_installed(name)
    s["dir"], s["dir_resolved"] = svc.get("dir", ""), str(to_path(svc["dir"]))
    s["models_dir_raw"] = svc.get("models_dir", "")
    s["homepage"] = svc.get("homepage", "")
    s["candidates"] = [] if s["installed"] else detect_candidates(name)
    if svc.get("scan"):   # フォルダ内の、まだプリセットにしていない起動スクリプト(サービスのフォルダからの相対)
        base = to_path(svc["dir"])
        s["unregistered"] = sorted(os.path.relpath(g, base) for g in glob.glob(str(base / svc["scan"])) if g not in known_cmds)
    return s


def full_state():
    presets = load_presets()
    known = {_abs_cmd(p) for p in presets if p.get("cmd") and p["service"] in services()}
    return {"services": {name: service_state(name, presets, known) for name in services()},
            "presets": presets, "ops": OPS, "models_root": str(ROOTS.models), "sets": load_sets(),
            "tokens": {k: token_source(k) for k in TOKENS}, "downloads": engine.public_jobs()}
