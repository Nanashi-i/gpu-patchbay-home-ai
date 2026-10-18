"""アプリの登録。サービス(machine.json の services.<名前>)が、どのアプリの知識で動くかを決める。

決め方: services.<名前>.app があればそれ。なければ、名前から(llama / strata / comfy / forge)、
それでも決まらなければ、type で(llama → llama、それ以外 → 汎用のスクリプト)。
"""
from ..core.config import service
from .base import App, ScriptApp
from .comfyui.app import ComfyApp
from .forge.app import ForgeApp
from .llama.app import LlamaApp
from .strata.app import StrataApp

APPS = {
    "llama": LlamaApp(),
    "strata": StrataApp(),
    "comfyui": ComfyApp(),
    "forge": ForgeApp(),
    "script": ScriptApp(),
}

_BY_NAME = {"llama": "llama", "strata": "strata", "comfy": "comfyui", "forge": "forge"}


def app_id_of(name):
    svc = service(name)
    aid = svc.get("app") or _BY_NAME.get(name) or ("llama" if svc.get("type") == "llama" else "script")
    return aid if aid in APPS else "script"


def app_for(name) -> App:
    return APPS[app_id_of(name)]
