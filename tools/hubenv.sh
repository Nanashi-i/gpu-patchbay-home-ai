# start.sh / stop.sh の共通部品(source して使う)。
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$(command -v python3)"
SERVICE=gpu-patchbay-home-ai

# 設定(machine.json)を読んで、HUB_STATE / HUB_HOST / HUB_PORT / HUB_AUTH を決める。誤りがあれば、その内容を出して終了する
load_info() {
  local out
  out="$("$PY" "$DIR/hub.py" --info 2>&1)" || { echo "$out" >&2; exit 1; }
  echo "$out" | grep -v '^HUB_' || true
  eval "$(echo "$out" | grep '^HUB_' | sed -E 's/^(HUB_[A-Z]+)=(.*)$/\1="\2"/')"
  PIDFILE="$HUB_STATE/hub.pid"
  LOGFILE="$HUB_STATE/hub.log"
}

# ハブ(このフォルダの hub.py)のプロセスが生きていれば、その PID を出す
hub_pid() {
  local pid
  pid="$(cat "$PIDFILE" 2>/dev/null)" || return 1
  [[ "$pid" =~ ^[0-9]+$ ]] || return 1
  tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null | grep -q "hub.py" || return 1
  echo "$pid"
}

# 画面を開く URL(host が 0.0.0.0 のときは、このPCの IP アドレスも出す)
hub_urls() {
  case "$HUB_HOST" in
    0.0.0.0|::|"") echo "http://127.0.0.1:$HUB_PORT"
                   local ip; ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
                   [ -n "$ip" ] && echo "http://$ip:$HUB_PORT" ;;
    *) echo "http://$HUB_HOST:$HUB_PORT" ;;
  esac
}

connect_host() {
  case "$HUB_HOST" in 0.0.0.0|::|"") echo 127.0.0.1 ;; *) echo "$HUB_HOST" ;; esac
}

port_open() { (exec 3<>"/dev/tcp/$(connect_host)/$HUB_PORT") 2>/dev/null; }

# systemd のサービスとして動いているか。ただし、**このフォルダの hub.py を起動するサービス**だけを対象にする
# (別のフォルダにクローンしたものから、別の場所のハブを、止めてしまわないため)。別の設定ファイルで試すとき(PATCHBAY_MACHINE)は、見ない
service_active() {
  [ -z "${PATCHBAY_MACHINE:-}" ] || return 1
  systemctl --user is-active --quiet "$SERVICE" 2>/dev/null || return 1
  systemctl --user show -p ExecStart --value "$SERVICE" 2>/dev/null | grep -qF "$DIR/hub.py"
}

# サービスが動いていて、ただし、別のフォルダのハブのとき(その場所を出す)
service_elsewhere() {
  [ -z "${PATCHBAY_MACHINE:-}" ] || return 1
  systemctl --user is-active --quiet "$SERVICE" 2>/dev/null || return 1
  service_active && return 1
  systemctl --user show -p ExecStart --value "$SERVICE" 2>/dev/null | grep -oE '[^ ]+/hub\.py' | head -1
}

service_pid() { systemctl --user show -p MainPID --value "$SERVICE" 2>/dev/null; }
