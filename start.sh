#!/usr/bin/env bash
# GPU Patchbay の起動(バックグラウンド)。停止は ./stop.sh
#   ./start.sh                     バックグラウンドで起動して、URL と PID を表示する
#   ./start.sh --foreground        いまのターミナルで起動する(Ctrl+C で止まる。動作の確認用)
#   ./start.sh --status            状態の確認
#   ./start.sh --install-service   PC の起動時に自動で立ち上がるよう、systemd のユーザーサービスに登録する
#   ./start.sh --uninstall-service  登録の解除
set -e
. "$(dirname "$0")/tools/hubenv.sh"

UNIT_DIR="$HOME/.config/systemd/user"
UNIT="$UNIT_DIR/$SERVICE.service"

show_urls() { hub_urls | sed 's/^/    /'; }

case "${1:-}" in
  -h|--help)
    sed -n '2,7p' "$0" | sed 's/^# \{0,1\}//'
    ;;
  --foreground)
    exec "$PY" "$DIR/hub.py"
    ;;
  --install-service)
    load_info
    if pid="$(hub_pid)"; then   # バックグラウンドで動いているハブは、サービスと、ポートを取り合うので、先に止める
      echo "バックグラウンドのハブ(PID: $pid)を止めて、サービスに切り替えます(起動済みのサービスは、止まりません)"
      "$DIR/stop.sh" >/dev/null
    fi
    mkdir -p "$UNIT_DIR"
    cat > "$UNIT" <<UNITEOF
[Unit]
Description=GPU Patchbay Home AI (local AI service launcher)
After=network.target

[Service]
ExecStart=$PY $DIR/hub.py
WorkingDirectory=$DIR
Restart=on-failure
RestartSec=3
# ハブを再起動しても、起動済みの llama-server 等は落とさない
KillMode=process

[Install]
WantedBy=default.target
UNITEOF
    systemctl --user daemon-reload
    systemctl --user enable --now "$SERVICE.service"
    echo "systemd のサービスとして登録しました。PC の起動時に、自動で立ち上がります。"
    echo "ログイン前から自動起動させるには(1回だけ): sudo loginctl enable-linger $USER"
    echo "停止: ./stop.sh   状態: ./start.sh --status   登録の解除: ./start.sh --uninstall-service"
    sleep 1
    show_urls
    ;;
  --uninstall-service)
    systemctl --user disable --now "$SERVICE.service" 2>/dev/null || true
    rm -f "$UNIT"
    systemctl --user daemon-reload
    echo "自動起動の登録を解除しました(ハブは止まりました。起動するには ./start.sh)"
    ;;
  --status)
    load_info
    if service_active; then
      echo "GPU Patchbay: systemd のサービスとして稼働中です(PID: $(service_pid))"
      show_urls
      echo "ログ: journalctl --user -u $SERVICE -f"
    elif pid="$(hub_pid)"; then
      echo "GPU Patchbay: バックグラウンドで稼働中です(PID: $pid)"
      show_urls
      echo "ログ: $LOGFILE"
    else
      echo "GPU Patchbay: 起動していません(起動: ./start.sh)"
      other="$(service_elsewhere)" && [ -n "$other" ] && echo "(別の場所のハブが、systemd のサービスとして稼働中です: $other)"
    fi
    systemctl --user is-enabled --quiet "$SERVICE" 2>/dev/null && echo "自動起動: 登録済み(解除: ./start.sh --uninstall-service)"
    exit 0
    ;;
  "")
    load_info
    if service_active; then
      echo "GPU Patchbay は、systemd のサービスとして、すでに稼働中です(PID: $(service_pid))"
      show_urls
      echo "止めるには ./stop.sh"
      exit 0
    fi
    if pid="$(hub_pid)"; then
      echo "GPU Patchbay は、すでに起動しています。PID: $pid"
      show_urls
      exit 0
    fi
    if port_open; then
      other="$(service_elsewhere)" && [ -n "$other" ] && echo "(別の場所のハブが、systemd のサービスとして稼働中です: $other)" >&2
      echo "ポート $HUB_PORT は、ほかのプログラムが使っています。machine.json の port を変えるか、そのプログラムを止めてください" >&2
      exit 1
    fi
    mkdir -p "$HUB_STATE"
    [ -f "$LOGFILE" ] && [ "$(stat -c %s "$LOGFILE")" -gt 1048576 ] && mv -f "$LOGFILE" "$LOGFILE.1"
    setsid "$PY" "$DIR/hub.py" >> "$LOGFILE" 2>&1 < /dev/null &
    pid=$!
    echo "$pid" > "$PIDFILE"
    for _ in $(seq 1 50); do    # 最大 10 秒、立ち上がりを待つ
      if ! kill -0 "$pid" 2>/dev/null; then
        rm -f "$PIDFILE"
        echo "GPU Patchbay の起動に失敗しました。ログの末尾:" >&2
        tail -n 15 "$LOGFILE" >&2
        exit 1
      fi
      port_open && break
      sleep 0.2
    done
    if ! port_open; then
      echo "GPU Patchbay は起動しましたが、まだ応答がありません(PID: $pid)。ログ: $LOGFILE" >&2
      exit 1
    fi
    echo "GPU Patchbay を起動しました。PID: $pid"
    show_urls
    [ "$HUB_AUTH" = none ] && [ "$HUB_HOST" != 127.0.0.1 ] && echo "注意: 認証なしで、LAN に公開しています(token の設定は任意です。README の「安全について」を参照)"
    echo "ログ: $LOGFILE   停止: ./stop.sh"
    ;;
  *)
    echo "使い方: ./start.sh [--foreground | --status | --install-service | --uninstall-service]" >&2
    exit 2
    ;;
esac
