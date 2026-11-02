#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN="$DIR/bin/xray"
if [ ! -f "$BIN" ] && command -v xray >/dev/null 2>&1; then
    BIN="$(command -v xray)"
fi

PID_FILE="$DIR/xray.pid"
LOG_FILE="$DIR/xray.log"

usage() {
    echo "Использование: $0 {start [сервер]|stop|restart [сервер]|status|test [сервер]|sub [URL]|list|settings}"
    exit 1
}

is_running() {
    if pgrep -f "$BIN.*active_config.json" >/dev/null 2>&1; then
        return 0
    fi
    return 1
}

case "$1" in
    start)
        if [ -n "$2" ]; then
            python3 "$DIR/core/manager.py" build "$2" >/dev/null
        elif [ ! -f "$DIR/active_config.json" ]; then
            python3 "$DIR/core/manager.py" build >/dev/null
        fi
        CFG="$DIR/active_config.json"

        if is_running; then
            echo "Прокси уже запущен. Сначала остановите: $0 stop"
            exit 1
        fi

        # Check for AmneziaVPN conflict
        if ip link show dev amn0 >/dev/null 2>&1; then
            echo "⚠️ Внимание: Обнаружен активный интерфейс AmneziaVPN (amn0)."
            echo "   При включенной Amnezia пакеты VLESS Reality могут фрагментироваться (MTU 1280 vs 1500)."
            echo "   Если интернет не работает через прокси, сначала отключите AmneziaVPN."
        fi

        # Check for port occupation
        for PORT in 10808 10809; do
            OCCUPIED_PID=$(lsof -ti :$PORT 2>/dev/null || ss -lptn "sport = :$PORT" 2>/dev/null | grep -oP 'pid=\K[0-9]+' | head -n 1 || true)
            if [ -n "$OCCUPIED_PID" ]; then
                PNAME=$(ps -p "$OCCUPIED_PID" -o comm= 2>/dev/null || echo "unknown")
                if [ "$PNAME" != "xray" ]; then
                    echo "⚠️ Предупреждение: Порт $PORT занят процессом $PNAME (PID $OCCUPIED_PID)!"
                fi
            fi
        done

        if [ ! -x "$BIN" ]; then
            echo "❌ Ошибка: бинарный файл Xray не найден по пути $BIN"
            echo "Установите xray ('sudo pacman -S xray') или запустите python3 setup.py"
            exit 1
        fi

        setsid -f "$BIN" run -c "$CFG" < /dev/null > "$LOG_FILE" 2>&1
        sleep 1

        if is_running; then
            X_PID=$(pgrep -f "$BIN.*active_config.json" | head -n 1)
            echo "$X_PID" > "$PID_FILE"
            INFO=$(python3 "$DIR/core/manager.py" status 2>/dev/null || echo "{}")
            SNAME=$(echo "$INFO" | grep -oP '"server_name":\s*"\K[^"]+' || echo "Default")
            DNAME=$(echo "$INFO" | grep -oP '"dns_name":\s*"\K[^"]+' || echo "Default")

            # Notify Hub server that client is connected
            HUB_URL=$(grep -oP '"hub_url":\s*"\K[^"]+' "$DIR/settings.json" 2>/dev/null || true)
            CLIENT_ID=$(grep -oP '"client_id":\s*"\K[^"]+' "$DIR/settings.json" 2>/dev/null || true)
            if [ -n "$HUB_URL" ] && [ -n "$CLIENT_ID" ]; then
                curl -s -m 2 "$HUB_URL/api/v1/heartbeat?client_id=$CLIENT_ID&status=connected" >/dev/null 2>&1 || true
            fi

            echo "✅ Прокси запущен локально (PID $X_PID):"
            echo "   - Сервер:     $SNAME"
            echo "   - DNS:        $DNAME"
            echo "   - SOCKS5:     127.0.0.1:10808"
            echo "   - HTTP Proxy: 127.0.0.1:10809"
            echo "   - Лог:        $LOG_FILE"
        else
            echo "❌ Ошибка запуска. Лог:"
            cat "$LOG_FILE"
            exit 1
        fi
        ;;

    restart)
        $0 stop
        sleep 1
        $0 start "$2"
        ;;

    settings)
        python3 "$DIR/core/manager.py" gui
        ;;

    sub)
        if [ -n "$2" ]; then
            python3 "$DIR/core/manager.py" sub "$2"
        else
            python3 "$DIR/core/manager.py" sub-update
        fi
        if is_running; then
            echo "🔄 Перезапуск прокси..."
            $0 restart >/dev/null
            echo "✅ Прокси перезапущен с новыми серверами."
        fi
        ;;

    stop)
        XPID=$(pgrep -f "$BIN.*active_config.json" | head -n 1 || true)
        BYTES_USED=0
        if [ -n "$XPID" ] && [ -r "/proc/$XPID/io" ]; then
            RCHAR=$(grep -oP '^rchar:\s*\K[0-9]+' "/proc/$XPID/io" 2>/dev/null || echo 0)
            WCHAR=$(grep -oP '^wchar:\s*\K[0-9]+' "/proc/$XPID/io" 2>/dev/null || echo 0)
            BYTES_USED=$(( RCHAR + WCHAR ))
        fi

        pkill -f "$BIN.*active_config.json" 2>/dev/null || true
        for _ in {1..20}; do
            if ! is_running; then break; fi
            sleep 0.1
        done
        if is_running; then
            pkill -9 -f "$BIN.*active_config.json" 2>/dev/null || true
        fi
        rm -f "$PID_FILE"

        # Notify Hub server that client disconnected with final session bytes
        HUB_URL=$(grep -oP '"hub_url":\s*"\K[^"]+' "$DIR/settings.json" 2>/dev/null || true)
        CLIENT_ID=$(grep -oP '"client_id":\s*"\K[^"]+' "$DIR/settings.json" 2>/dev/null || true)
        if [ -n "$HUB_URL" ] && [ -n "$CLIENT_ID" ]; then
            curl -s -m 2 "$HUB_URL/api/v1/disconnect?client_id=$CLIENT_ID&bytes_used=$BYTES_USED" >/dev/null 2>&1 || true
        fi

        echo "🛑 Прокси остановлен."
        ;;

    status)
        if is_running; then
            X_PID=$(pgrep -f "$BIN.*active_config.json" | head -n 1)
            echo "🟢 Прокси активен (PID ${X_PID:-unknown})."
            echo "   SOCKS5:     127.0.0.1:10808"
            echo "   HTTP Proxy: 127.0.0.1:10809"
        else
            echo "⚪ Прокси не запущен."
        fi
        ;;

    test)
        if ! is_running; then
            echo "Прокси не запущен. Запускаем на лету..."
            "$0" start "$2" >/dev/null
            WAS_STOPPED=1
        fi

        echo "🔍 Тестирование через SOCKS5 (127.0.0.1:10808)..."
        IP_SOCKS=$(curl -s -m 5 -x socks5h://127.0.0.1:10808 https://api.ipify.org || echo "FAIL")
        echo "   Внешний IP: $IP_SOCKS"

        echo "🔍 Тестирование через HTTP Proxy (127.0.0.1:10809)..."
        IP_HTTP=$(curl -s -m 5 -x http://127.0.0.1:10809 https://api.ipify.org || echo "FAIL")
        echo "   Внешний IP: $IP_HTTP"

        if [ "$WAS_STOPPED" = "1" ]; then
            "$0" stop >/dev/null
        fi
        ;;

    list)
        echo "Доступные серверы:"
        python3 -c "
import json, os
p = '$DIR/servers.json'
if os.path.exists(p):
    with open(p) as f:
        data = json.load(f)
    for s in data:
        print(f' - {s[\"id\"]}: {s[\"name\"]}')
else:
    for f in os.listdir('$DIR/configs'):
        if f.endswith('.json'):
            print(' - ' + f[:-5])
" 2>/dev/null || ls "$DIR"/configs/*.json 2>/dev/null
        ;;

    *)
        usage
        ;;
esac
