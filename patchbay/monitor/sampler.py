"""モニターのサンプラー: 一定間隔で、PC とアプリの状態を記録する(メモリ上だけ。ハブの停止でリセット)。

サンプル(1点)は、名前付きの辞書:
  {t, cpu, mem, swap, disk_read, disk_write, disk_used, gpus:[{util, vram, temp, power}], apps:{アプリID: {...}}}
  単位: cpu=% / mem・swap・disk_used=GB / disk_*=MB/s / vram=MB / temp=℃ / power=W
  apps には、動いているアプリの固有の指標が入る(例: llama の /metrics。apps/*/ の stats())。
"""
import os
import shutil
import threading
import time
from collections import deque
from pathlib import Path

from ..core.config import CFG, HOME, ROOTS, services
from . import system


class Sampler:
    def __init__(self, interval=5.0, hours=3.0):
        self.interval = max(1.0, float(interval))
        self.hours = float(hours)
        self.samples = deque(maxlen=max(10, int(self.hours * 3600 / self.interval)))
        self.meta = {}
        path = ROOTS.models if ROOTS.models.exists() else Path(HOME)
        self.path = path
        st = os.stat(path).st_dev
        self.dev = (os.major(st), os.minor(st))
        self._prev_cpu = self._prev_disk = None
        self._prev_t = time.time()

    # ---- 準備: 変わらない情報(meta)と、差分を取るための初期値
    def prime(self):
        mi = system.meminfo()
        self._prev_cpu, self._prev_disk, self._prev_t = system.cpu_times(), system.disk_counters(self.dev), time.time()
        self.meta.update({"interval": self.interval, "hours": self.hours, "cpus": os.cpu_count(),
                          "mem_total_gb": mi["MemTotal"] / 1048576, "disk_has_io": self._prev_disk is not None,
                          "pc": system.pc_info(), "gpus": self._gpu_meta(system.nvidia())})

    @staticmethod
    def _gpu_meta(gpus):
        return [{"name": g["name"], "mem_total": g["mem_total"], "power_limit": g["power_limit"]} for g in gpus]

    # ---- 1点を読む
    def sample(self):
        now = time.time()
        cpu = system.cpu_times()
        dt_total = cpu[0] - self._prev_cpu[0]
        cpu_pct = 100.0 * (1 - (cpu[1] - self._prev_cpu[1]) / dt_total) if dt_total > 0 else 0.0
        self._prev_cpu = cpu
        mi = system.meminfo()
        disk = system.disk_counters(self.dev)
        rd = wr = None
        if disk and self._prev_disk and now > self._prev_t:
            span = now - self._prev_t
            rd, wr = (disk[0] - self._prev_disk[0]) / span / 1048576, (disk[1] - self._prev_disk[1]) / span / 1048576
        self._prev_disk, self._prev_t = disk, now
        du = shutil.disk_usage(self.path)
        gpus = system.nvidia()
        self.meta.update({"mem_total_gb": mi["MemTotal"] / 1048576, "disk_total_gb": du.total / 1073741824,
                          "disk_path": str(self.path), "swap_total_gb": mi.get("SwapTotal", 0) / 1048576,
                          "gpus": self._gpu_meta(gpus)})
        return {"t": round(now, 1), "cpu": round(cpu_pct, 1),
                "mem": round((mi["MemTotal"] - mi["MemAvailable"]) / 1048576, 2),
                "swap": round((mi.get("SwapTotal", 0) - mi.get("SwapFree", 0)) / 1048576, 2),
                "disk_read": None if rd is None else round(rd, 2), "disk_write": None if wr is None else round(wr, 2),
                "disk_used": round(du.used / 1073741824, 1),
                "gpus": [{"util": g["util"], "vram": g["mem_used"], "temp": g["temp"], "power": g["power"]} for g in gpus],
                "apps": collect_app_stats()}

    def run(self):
        self.prime()
        while True:
            time.sleep(self.interval)
            try:
                self.samples.append(self.sample())
            except Exception as e:  # noqa: BLE001
                print(f"[patchbay] monitor 失敗: {e}", flush=True)

    def snapshot(self, since):
        return {"meta": self.meta, "samples": [s for s in list(self.samples) if s["t"] > since], "now": time.time()}


def collect_app_stats():
    """動いているアプリの、固有の指標(apps/*/ の stats())。{アプリID: 指標}"""
    from ..apps import app_for
    out = {}
    for name in services():
        app = app_for(name)
        if not CFG["services"][name].get("enabled", True):
            continue
        s = app.stats(name)
        if s is not None and app.app_id not in out:   # 同じアプリが複数あっても、最初の1つだけ
            out[app.app_id] = s
    return out


SAMPLER = None


def start():
    """サンプラーを作って、スレッドで動かす。"""
    global SAMPLER
    mc = CFG.get("monitor", {})
    SAMPLER = Sampler(mc.get("interval_sec", 5), mc.get("history_hours", 3))
    threading.Thread(target=SAMPLER.run, daemon=True).start()
    return SAMPLER
