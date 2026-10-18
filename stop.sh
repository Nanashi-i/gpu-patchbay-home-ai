#!/usr/bin/env bash
# GPU Patchbay の停止。起動済みの llama-server / ComfyUI などは、止めません(止めるのは、画面の「停止」)。
set -e
. "$(dirname "$0")/tools/hubenv.sh"
load_info

if service_active; then
  pid="$(service_pid)"
  systemctl --user stop "$SERVICE"
  echo "GPU Patchbay(systemd のサービス)を停止しました。PID: $pid"
  systemctl --user is-enabled --quiet "$SERVICE" 2>/dev/null && echo "自動起動の登録は、残っています(次回のログイン / 起動時に立ち上がります。解除: ./start.sh --uninstall-service)"
  exit 0
fi

if ! pid="$(hub_pid)"; then
  rm -f "$PIDFILE"
  echo "GPU Patchbay は、起動していません"
  exit 0
fi

kill -TERM "$pid"
for _ in $(seq 1 50); do   # 最大 10 秒
  kill -0 "$pid" 2>/dev/null || break
  sleep 0.2
done
if kill -0 "$pid" 2>/dev/null; then
  kill -KILL "$pid" 2>/dev/null || true
  echo "応答がなかったため、強制終了しました。PID: $pid"
else
  echo "GPU Patchbay を停止しました。PID: $pid"
fi
rm -f "$PIDFILE"
echo "(起動済みの llama-server などは、止めていません)"
