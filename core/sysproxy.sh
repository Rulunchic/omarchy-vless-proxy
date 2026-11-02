#!/usr/bin/env bash
set -e

PROXY_HTTP="http://127.0.0.1:10809"
PROXY_SOCKS="socks5h://127.0.0.1:10808"
NO_PROXY="localhost,127.0.0.1,localaddress,.localdomain.com,::1,*.ru,*.su,*.рф,*.xn--p1ai,vk.com,*.vk.com,max.ru,*.max.ru,ya.ru,*.ya.ru,yandex.ru,*.yandex.ru,habr.com,*.habr.com,2gis.com,*.2gis.com,ozon.ru,*.ozon.ru,wildberries.ru,*.wildberries.ru,avito.ru,*.avito.ru,gosuslugi.ru,*.gosuslugi.ru"
IGNORE_HOSTS="['localhost', '127.0.0.0/8', '::1', '*.ru', '*.su', '*.xn--p1ai', '*.рф', 'vk.com', '*.vk.com', 'max.ru', '*.max.ru', 'ya.ru', '*.ya.ru', 'yandex.ru', '*.yandex.ru', 'habr.com', '*.habr.com', '2gis.com', '*.2gis.com', 'gosuslugi.ru', '*.gosuslugi.ru', 'ozon.ru', '*.ozon.ru', 'wildberries.ru', '*.wildberries.ru', 'avito.ru', '*.avito.ru']"

case "$1" in
    on|enable)
        # 1. GSettings (GNOME / GTK / Chromium / Electron)
        if command -v gsettings >/dev/null 2>&1; then
            gsettings set org.gnome.system.proxy mode 'manual'
            gsettings set org.gnome.system.proxy.http host '127.0.0.1'
            gsettings set org.gnome.system.proxy.http port 10809
            gsettings set org.gnome.system.proxy.https host '127.0.0.1'
            gsettings set org.gnome.system.proxy.https port 10809
            gsettings set org.gnome.system.proxy.socks host '127.0.0.1'
            gsettings set org.gnome.system.proxy.socks port 10808
            gsettings set org.gnome.system.proxy ignore-hosts "$IGNORE_HOSTS"
        fi

        # 2. Динамическое обновление systemd user сессии
        systemctl --user set-environment \
            http_proxy="$PROXY_HTTP" \
            https_proxy="$PROXY_HTTP" \
            all_proxy="$PROXY_SOCKS" \
            HTTP_PROXY="$PROXY_HTTP" \
            HTTPS_PROXY="$PROXY_HTTP" \
            ALL_PROXY="$PROXY_SOCKS" \
            no_proxy="$NO_PROXY" \
            NO_PROXY="$NO_PROXY" 2>/dev/null || true

        rm -f "$HOME/.config/environment.d/99-proxy.conf"

        # 3. LibreWolf Flatpak GSettings keyfile sync
        LW_KEYFILE="$HOME/.var/app/io.gitlab.librewolf-community/config/glib-2.0/settings/keyfile"
        if [ -d "$(dirname "$LW_KEYFILE")" ]; then
            cat <<EOF > "$LW_KEYFILE"
[system/proxy]
mode='manual'
ignore-hosts=$IGNORE_HOSTS

[system/proxy/http]
host='127.0.0.1'
port=10809

[system/proxy/https]
host='127.0.0.1'
port=10809

[system/proxy/socks]
host='127.0.0.1'
port=10808
EOF
        fi

        echo "✅ Системный прокси включен (GSettings manual + systemd):"
        echo "   HTTP:  $PROXY_HTTP"
        echo "   SOCKS: $PROXY_SOCKS"
        ;;

    off|disable)
        # 1. GSettings -> прямое соединение
        if command -v gsettings >/dev/null 2>&1; then
            gsettings set org.gnome.system.proxy mode 'none'
        fi

        # 2. Очистка переменных в systemd user сессии
        systemctl --user set-environment \
            http_proxy="" \
            https_proxy="" \
            all_proxy="" \
            HTTP_PROXY="" \
            HTTPS_PROXY="" \
            ALL_PROXY="" \
            no_proxy="" \
            NO_PROXY="" 2>/dev/null || true

        rm -f "$HOME/.config/environment.d/99-proxy.conf"

        # 3. LibreWolf Flatpak GSettings keyfile sync -> direct
        LW_KEYFILE="$HOME/.var/app/io.gitlab.librewolf-community/config/glib-2.0/settings/keyfile"
        if [ -f "$LW_KEYFILE" ]; then
            cat <<EOF > "$LW_KEYFILE"
[system/proxy]
mode='none'
EOF
        fi

        echo "🛑 Системный прокси отключен (прямое подключение к интернету)."
        ;;

    status)
        MODE="none"
        if command -v gsettings >/dev/null 2>&1; then
            MODE=$(gsettings get org.gnome.system.proxy mode 2>/dev/null || echo "none")
        fi
        echo "GSettings режим: $MODE"
        ;;

    *)
        echo "Использование: $0 {on|off|status}"
        exit 1
        ;;
esac
