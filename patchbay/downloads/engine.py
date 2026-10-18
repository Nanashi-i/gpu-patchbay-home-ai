"""ダウンロードの仕組み: URL の解析・ジョブのキュー・途中再開・完了後の処理。

アプリごとに違う部分(保存先・拡張子・種別の推定・共有リンク・セットへの追加)は、
apps/*/ の download_rules() が返すルール(downloads/rules.py)に任せる。
ジョブは、1つずつ順番に処理する(スレッド1つ)。.part に書き、続きから再開できる。
"""
import json
import os
import queue
import secrets
import shutil
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from ..core.config import services
from ..core.errors import HubError
from .hf import OPENER, auth_headers, check_public_host, parse_hf

ALLOWED_SCHEMES = ("http", "https")   # file:// などで、ハブのPCのファイルを読ませない(テストだけが、広げる)
DL = {}                  # ジョブ id -> ジョブ(state: queued / downloading / done / error / cancelled)
DL_Q = queue.Queue()
dl_lock = threading.Lock()   # キューへの登録(保存先の重複の確認と、ジョブの追加)を、1つずつにする
MAX_ACTIVE_JOBS = 500        # 待機中・ダウンロード中のジョブの上限
LOW_DISK = 1 << 30           # 空きがこれを下回ったら、転送を止める(サイズ不明の転送も守る)


def _rules(name):
    from ..apps import app_for   # 循環を避けるため、使うときに読み込む
    return app_for(name).download_rules(name)


def _check_scheme(url):
    if urllib.parse.urlparse(url or "").scheme not in ALLOWED_SCHEMES:
        raise HubError("http:// か https:// の URL だけ使えます")
    if urllib.parse.urlparse(url).scheme in ("http", "https"):
        check_public_host(url)


def inspect(url, name):
    """URL を解析して、ファイルの一覧と、推定した種別を返す。"""
    if name not in services():
        raise HubError("保存先サービスを選んでください")
    rules = _rules(name)
    exts, cats = rules.exts(), rules.categories()
    _check_scheme(url)
    hf = parse_hf(url)
    if not hf:
        fname = Path(urllib.parse.urlparse(url).path).name
        ok = Path(fname).suffix.lower() in exts
        category = (rules.guess(fname) if ok else cats[0]["key"]) if cats else None
        return {"service": name, "direct": True, "url": url, "folder": "", "categories": cats,
                "files": [{"path": fname if ok else "", "size": None, "category": category}],
                "preselect": [fname if ok else ""], "need_name": not ok, "allowed": sorted(exts)}
    repo, rev, path = hf
    api = f"https://huggingface.co/api/models/{repo}/tree/{urllib.parse.quote(rev, safe='')}?recursive=1"
    try:
        with OPENER.open(urllib.request.Request(api, headers=auth_headers(api)), timeout=30) as r:
            tree = json.load(r)
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise HubError("このリポジトリは認証が必要です(非公開または gated)。「🔑 トークン」でHFトークンを登録し、HFのページで利用規約に同意してください") from None
        raise HubError(f"HF API エラー: {e.code}") from None
    except Exception as e:  # noqa: BLE001
        raise HubError(f"HF API 取得失敗: {e}") from None
    files = [{"path": t["path"], "size": (t.get("lfs") or {}).get("size", t.get("size")),
              "category": rules.guess(t["path"]) if cats else None}
             for t in tree if t.get("type") == "file" and Path(t["path"]).suffix.lower() in exts]
    if not files:
        raise HubError(f"このリポジトリに {', '.join(sorted(exts))} のファイルが見つかりません")
    return {"service": name, "direct": False, "repo": repo, "rev": rev, "folder": rules.default_folder(repo.split("/")[1]),
            "categories": cats, "files": files, "preselect": [path] if path else []}


def enqueue(body):
    """ジョブをキューに追加する。保存先の検証(モデル置き場の外・拡張子・既存)は、ルールが行う。
    すべての検証が終わってから、セットの作成とジョブの登録をする(途中で失敗したら、何も変えない)。"""
    name = body.get("service")
    if name not in services():
        raise HubError("保存先サービスを選んでください")
    rules = _rules(name)
    folder = (body.get("folder") or "").strip().strip("/")
    jobs = []
    for it in body.get("files", []):
        path = it["path"] if isinstance(it, dict) else it
        if not path:
            raise HubError("ファイル名を入力してください")
        dest, cat = rules.dest(it, folder)
        if body.get("repo"):
            url = (f"https://huggingface.co/{body['repo']}/resolve/{urllib.parse.quote(body.get('rev', 'main'), safe='')}"
                   f"/{urllib.parse.quote(path)}")
        else:
            url = body.get("url")
            _check_scheme(url)
        jobs.append((url, dest, Path(path).name, cat))
    if not jobs:
        raise HubError("ファイルが選択されていません")
    with dl_lock:
        busy = {j["dest"] for j in DL.values() if j["state"] in ("queued", "downloading")}
        if len(busy) + len(jobs) > MAX_ACTIVE_JOBS:
            raise HubError(f"待機中のダウンロードが多すぎます(最大 {MAX_ACTIVE_JOBS} 件)")
        seen = set()
        for _, dest, label, _ in jobs:
            if str(dest) in busy or str(dest) in seen:
                raise HubError(f"同じ保存先へのダウンロードが、すでにあります: {label}")
            seen.add(str(dest))
        opts = rules.job_options(body)   # 新しいセットの作成など(検証が全部通ってから)
        for url, dest, label, cat in jobs:
            jid = secrets.token_hex(4)
            DL[jid] = {"id": jid, "name": label, "dest": str(dest), "service": name, "category": cat, "state": "queued",
                       "done": 0, "total": 0, "speed": 0, "error": "", "cancel": False,
                       "link": bool(opts["link"] and cat), "set": opts["set"] if cat else None}
            DL_Q.put((jid, url, dest))


def cancel(jid):
    if jid in DL:
        DL[jid]["cancel"] = True


def clear_finished():
    for k in [k for k, v in DL.items() if v["state"] in ("done", "error", "cancelled")]:
        del DL[k]


def public_jobs():
    return [{k: v for k, v in j.items() if k != "cancel"} for j in DL.values()]


def _finish(j, dest):
    _rules(j["service"]).on_done(j, dest)


def _open_part(part, mode):
    """.part を開く。リンクは辿らない(モデル置き場の外のファイルを、上書きさせない)。"""
    flags = os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW | (os.O_APPEND if mode == "ab" else os.O_TRUNC)
    return os.fdopen(os.open(part, flags, 0o644), mode)


def _download(jid, url, dest):
    j = DL[jid]
    if j["cancel"]:
        j["state"] = "cancelled"
        return
    part = dest.with_name(dest.name + ".part")
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        if part.is_symlink():
            raise HubError(f"{part.name} がリンクです。保存先の安全のため、中止しました(削除してから、やり直してください)")
        pos = part.stat().st_size if part.exists() else 0
        h = auth_headers(url)
        if pos:
            h["Range"] = f"bytes={pos}-"
        j["state"] = "downloading"
        check_public_host(url)
        try:
            r = OPENER.open(urllib.request.Request(url, headers=h), timeout=30)
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise HubError("認証が必要です(gated/非公開)。「🔑 トークン」でトークンを登録し、HFのページで利用規約に同意してください")
            if e.code == 416 and pos:  # .part が既に完全
                _commit(part, dest)
                j.update(state="done", done=pos, total=pos)
                _finish(j, dest)
                return
            raise
        with r:
            clen = int(r.headers.get("Content-Length") or 0)
            if r.status == 206:
                total, mode = pos + clen, "ab"
            else:
                total, pos, mode = clen, 0, "wb"
            free = shutil.disk_usage(dest.parent).free
            if total and total - pos > free - LOW_DISK:
                raise HubError(f"空き容量不足(必要 {(total - pos) >> 20}MB / 空き {free >> 20}MB)")
            j.update(total=total, done=pos)
            last_t, last_b, last_check = time.time(), pos, pos
            with _open_part(part, mode) as f:
                while True:
                    if j["cancel"]:
                        j["state"] = "cancelled"
                        return
                    chunk = r.read(1 << 20)
                    if not chunk:
                        break
                    f.write(chunk)
                    j["done"] += len(chunk)
                    now = time.time()
                    if now - last_t >= 1:
                        j["speed"] = (j["done"] - last_b) / (now - last_t)
                        last_t, last_b = now, j["done"]
                    if j["done"] - last_check >= (64 << 20):   # サイズ不明でも、ディスクを使い切らない
                        last_check = j["done"]
                        if shutil.disk_usage(dest.parent).free < LOW_DISK:
                            raise HubError("空き容量が足りなくなったため、中止しました(続きから再開できます)")
        if total and j["done"] != total:
            raise HubError("サイズ不一致(途中切断)。再実行すると続きから再開します")
        _commit(part, dest)
        _finish(j, dest)
        j.update(state="done", speed=0)
    except Exception as e:  # noqa: BLE001
        j.update(state="error", error=str(e), speed=0)


def _commit(part, dest):
    """完成した .part を、本来の名前にする。すでにあるファイルは、上書きしない。"""
    if dest.exists() or dest.is_symlink():
        raise HubError(f"既に存在するため、保存しませんでした: {dest.name}(.part は残してあります)")
    part.replace(dest)


def run_next():
    """キューから1件を取り出して実行する。どんな失敗も、そのジョブの失敗にとどめる(後ろのジョブを止めない)。"""
    jid, url, dest = DL_Q.get()
    try:
        _download(jid, url, dest)
    except BaseException as e:  # noqa: BLE001
        DL[jid].update(state="error", error=f"{type(e).__name__}: {e}", speed=0)


def dl_worker():
    while True:
        run_next()
