"""PC の状態の読み取り(Linux の /proc と nvidia-smi。どれも、軽い読み取りだけ)。"""
import platform
import socket
import subprocess
from pathlib import Path


def cpu_times():
    with open("/proc/stat") as f:
        v = [int(x) for x in f.readline().split()[1:9]]
    return sum(v), v[3] + v[4]  # total, idle(+iowait)


def meminfo():
    d = {}
    with open("/proc/meminfo") as f:
        for line in f:
            k, _, rest = line.partition(":")
            d[k] = int(rest.split()[0])  # kB
    return d


def disk_counters(dev):
    if not dev:
        return None
    try:
        with open("/proc/diskstats") as f:
            for line in f:
                p = line.split()
                if int(p[0]) == dev[0] and int(p[1]) == dev[1]:
                    return int(p[5]) * 512, int(p[9]) * 512  # 読み / 書き (bytes)
    except (OSError, ValueError, IndexError):
        pass
    return None


def nvidia():
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=index,name,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw,power.limit",
                              "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=5).stdout
    except Exception:  # noqa: BLE001
        return []
    gpus = []
    for line in out.strip().splitlines():
        p = [x.strip() for x in line.split(",")]
        if len(p) < 8:
            continue

        def num(x):
            try:
                return float(x)
            except ValueError:
                return None
        gpus.append({"name": p[1], "util": num(p[2]), "mem_used": num(p[3]), "mem_total": num(p[4]), "temp": num(p[5]),
                     "power": num(p[6]), "power_limit": num(p[7])})
    return gpus


def pc_info():
    """このPCの情報(起動時に1回だけ取得)。"""
    info = {"hostname": socket.gethostname(), "os": "", "kernel": platform.release(), "arch": platform.machine(),
            "cpu_model": "", "cores": None, "gpu_driver": ""}
    try:
        for line in Path("/etc/os-release").read_text().splitlines():
            if line.startswith("PRETTY_NAME="):
                info["os"] = line.split("=", 1)[1].strip().strip('"')
    except OSError:
        info["os"] = platform.system()
    try:
        pairs, model = set(), ""
        phys = core = None
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            k, _, v = line.partition(":")
            k, v = k.strip(), v.strip()
            if k == "model name" and not model:
                model = v
            elif k == "physical id":
                phys = v
            elif k == "core id":
                core = v
                pairs.add((phys, core))
        info["cpu_model"] = model
        info["cores"] = len(pairs) or None
    except OSError:
        pass
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"], capture_output=True, text=True, timeout=5).stdout
        info["gpu_driver"] = out.strip().splitlines()[0].strip() if out.strip() else ""
    except Exception:  # noqa: BLE001
        pass
    return info
