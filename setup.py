#!/usr/bin/env python3
"""
Omarchy VLESS Proxy Setup & Installer
Parses BeregVPN (or any VLESS) subscription, downloads Xray binary,
installs Omarchy bar widget, and configures proxy management.
"""

import os
import sys
import json
import base64
import urllib.request
import urllib.parse
import re
import stat
import zipfile
import shutil
import subprocess
import argparse

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIGS_DIR = os.path.join(ROOT_DIR, "configs")
BIN_DIR = os.path.join(ROOT_DIR, "bin")
CORE_DIR = os.path.join(ROOT_DIR, "core")
SERVERS_JSON = os.path.join(ROOT_DIR, "servers.json")

XRAY_RELEASE_URL = "https://github.com/XTLS/Xray-core/releases/download/v24.10.31/Xray-linux-64.zip"

def log(msg, symbol="ℹ️"):
    print(f"{symbol} {msg}")

def ensure_dirs():
    os.makedirs(CONFIGS_DIR, exist_ok=True)
    os.makedirs(BIN_DIR, exist_ok=True)
    os.makedirs(CORE_DIR, exist_ok=True)

def fetch_subscription(url_or_content):
    """Fetch subscription from URL or read from string/file."""
    content = ""
    if os.path.isfile(url_or_content):
        with open(url_or_content, "r", encoding="utf-8") as f:
            content = f.read().strip()
    elif url_or_content.startswith("http://") or url_or_content.startswith("https://"):
        log(f"Загрузка подписки из {url_or_content}...")
        req = urllib.request.Request(
            url_or_content,
            headers={"User-Agent": "curl/8.0.0"}
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                content = resp.read().decode("utf-8", errors="ignore").strip()
        except Exception as e:
            log(f"Ошибка загрузки по сети: {e}. Пробуем curl...", "⚠️")
            res = subprocess.run(["curl", "-s", "-m", "15", url_or_content], capture_output=True, text=True)
            content = res.stdout.strip()
    else:
        content = url_or_content.strip()

    # Check if base64 encoded
    try:
        padded = content + "=" * ((4 - len(content) % 4) % 4)
        decoded = base64.b64decode(padded).decode("utf-8", errors="ignore")
        if "vless://" in decoded:
            return decoded
    except Exception:
        pass

    return content

def slugify(text):
    """Generate safe filename slug from server name."""
    t = text.lower()
    mapping = {
        "германия": "germany", "germany": "germany", "de": "germany",
        "финляндия": "finland", "finland": "finland", "fi": "finland",
        "сша": "usa", "usa": "usa", "us": "usa",
        "эстония": "estonia", "estonia": "estonia", "ee": "estonia",
        "польша": "poland", "poland": "poland", "pl": "poland",
        "нидерланды": "netherlands", "netherlands": "netherlands", "nl": "netherlands",
        "россия": "russia", "russia": "russia", "ru": "russia",
        "франция": "france", "france": "france", "fr": "france",
        "турция": "turkey", "turkey": "turkey", "tr": "turkey"
    }
    for k, v in mapping.items():
        if k in t:
            return v
    # Fallback to alphanumeric
    slug = re.sub(r'[^a-zA-Z0-9_]+', '_', t).strip('_')
    return slug if slug else "server"

def parse_vless_url(vless_url):
    """Parse vless:// URL into Xray outbound config."""
    p = urllib.parse.urlparse(vless_url)
    if p.scheme != "vless":
        return None

    uuid = p.username
    address = p.hostname
    port = p.port or 443
    raw_query = urllib.parse.parse_qs(p.query)
    q = {k: v[0] for k, v in raw_query.items()}
    fragment = urllib.parse.unquote(p.fragment).strip() if p.fragment else address

    flow = q.get("flow", "")
    encryption = q.get("encryption", "none")
    security = q.get("security", "none")
    net_type = q.get("type", "tcp")

    stream_settings = {
        "network": net_type,
        "security": security
    }

    if security == "reality":
        reality_settings = {
            "show": False,
            "fingerprint": q.get("fp", "chrome"),
            "serverName": q.get("sni", address),
            "publicKey": q.get("pbk", ""),
            "shortId": q.get("sid", ""),
            "spiderX": q.get("spx", "/")
        }
        stream_settings["realitySettings"] = reality_settings
    elif security == "tls":
        tls_settings = {
            "serverName": q.get("sni", address),
            "fingerprint": q.get("fp", "chrome")
        }
        if "alpn" in q:
            tls_settings["alpn"] = q["alpn"].split(",")
        stream_settings["tlsSettings"] = tls_settings

    if net_type == "xhttp":
        stream_settings["xhttpSettings"] = {
            "path": q.get("path", "/"),
            "host": q.get("host", address),
            "mode": q.get("mode", "packet-up")
        }
    elif net_type == "ws":
        stream_settings["wsSettings"] = {
            "path": q.get("path", "/"),
            "headers": {"Host": q.get("host", address)}
        }

    user_obj = {
        "id": uuid,
        "encryption": encryption
    }
    if flow:
        user_obj["flow"] = flow

    outbound = {
        "protocol": "vless",
        "settings": {
            "vnext": [
                {
                    "address": address,
                    "port": port,
                    "users": [user_obj]
                }
            ]
        },
        "streamSettings": stream_settings,
        "tag": "proxy"
    }

    return {
        "name": fragment,
        "host": address,
        "port": port,
        "outbound": outbound,
        "raw_url": vless_url
    }

def build_full_config(outbound):
    """Wrap single outbound in full Xray config."""
    return {
        "log": {
            "loglevel": "warning"
        },
        "inbounds": [
            {
                "tag": "socks",
                "listen": "127.0.0.1",
                "port": 10808,
                "protocol": "socks",
                "settings": {
                    "auth": "noauth",
                    "udp": True
                },
                "sniffing": {
                    "enabled": True,
                    "destOverride": ["http", "tls"]
                }
            },
            {
                "tag": "http",
                "listen": "127.0.0.1",
                "port": 10809,
                "protocol": "http"
            }
        ],
        "outbounds": [
            outbound,
            {
                "protocol": "freedom",
                "tag": "direct"
            }
        ]
    }

def process_subscription(sub_content):
    """Extract and generate JSON files for all servers in subscription."""
    lines = sub_content.splitlines()
    parsed_servers = []
    keys_text = ["# VLESS Keys extracted from subscription\n"]

    used_ids = {}

    for line in lines:
        line = line.strip()
        if not line or not line.startswith("vless://"):
            continue

        item = parse_vless_url(line)
        if not item:
            continue

        base_id = slugify(item["name"])
        count = used_ids.get(base_id, 0)
        used_ids[base_id] = count + 1
        sid = base_id if count == 0 else f"{base_id}_{count+1}"

        # Add Google/AI badge to Finland
        display_name = item["name"]
        if sid == "finland" and "Google" not in display_name:
            display_name = f"{display_name} (Google/AI)"

        filename = f"{sid}.json"
        cfg_path = os.path.join(CONFIGS_DIR, filename)

        full_cfg = build_full_config(item["outbound"])
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(full_cfg, f, indent=2, ensure_ascii=False)

        parsed_servers.append({
            "id": sid,
            "name": display_name,
            "file": filename,
            "host": item["host"]
        })

        keys_text.append(f"## {display_name}\n{line}\n")

    # Save servers.json
    with open(SERVERS_JSON, "w", encoding="utf-8") as f:
        json.dump(parsed_servers, f, indent=2, ensure_ascii=False)

    # Save keys.txt
    with open(os.path.join(ROOT_DIR, "keys.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(keys_text))

    log(f"Успешно обработано серверов: {len(parsed_servers)}", "✅")
    for s in parsed_servers:
        log(f" - [{s['id']}] {s['name']} -> configs/{s['file']}")

    return parsed_servers

def ensure_xray_binary():
    """Ensure Xray binary is present in bin/xray or system."""
    xray_bin = os.path.join(BIN_DIR, "xray")
    if os.path.exists(xray_bin) and os.access(xray_bin, os.X_OK):
        log("Xray бинарник уже присутствует в bin/xray", "✅")
        return xray_bin

    # Check system xray
    sys_xray = shutil.which("xray")
    if sys_xray:
        log(f"Найден системный Xray ({sys_xray}), копируем в bin/xray...", "ℹ️")
        shutil.copy2(sys_xray, xray_bin)
        os.chmod(xray_bin, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
        return xray_bin

    # Download official binary
    log(f"Загрузка официального Xray ({XRAY_RELEASE_URL})...", "⬇️")
    zip_path = os.path.join(BIN_DIR, "xray.zip")
    urllib.request.urlretrieve(XRAY_RELEASE_URL, zip_path)

    log("Распаковка Xray...", "📦")
    with zipfile.ZipFile(zip_path, 'r') as zf:
        zf.extract("xray", BIN_DIR)

    os.chmod(xray_bin, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
    if os.path.exists(zip_path):
        os.remove(zip_path)

    log("Xray успешно установлен в bin/xray", "✅")
    return xray_bin

def install_system_components():
    """Install bin wrappers, Omarchy plugin, and update shell configs."""
    home = os.path.expanduser("~")
    user_bin = os.path.join(home, ".local", "bin")
    os.makedirs(user_bin, exist_ok=True)

    # Make core scripts executable
    for f in ["proxy.sh", "sysproxy.sh"]:
        p = os.path.join(CORE_DIR, f)
        if os.path.exists(p):
            os.chmod(p, os.stat(p).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    # Install CLI wrappers into ~/.local/bin
    wrappers = ["zapret-toggle", "zapret-status", "zapret-settings"]
    for w in wrappers:
        src = os.path.join(ROOT_DIR, "bin", w)
        dst = os.path.join(user_bin, w)
        if os.path.exists(src):
            shutil.copy2(src, dst)
            os.chmod(dst, os.stat(dst).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            log(f"Установлен CLI скрипт: {dst}")

    # Install Omarchy plugin
    plugin_dir = os.path.join(home, ".config", "omarchy", "plugins", "bobol.zapret")
    os.makedirs(plugin_dir, exist_ok=True)
    for f in ["manifest.json", "Zapret.qml"]:
        src = os.path.join(ROOT_DIR, "plugin", f)
        dst = os.path.join(plugin_dir, f)
        if os.path.exists(src):
            shutil.copy2(src, dst)
            log(f"Обновлен плагин Omarchy: {dst}")

    # Ensure bobol.zapret is registered in ~/.config/omarchy/shell.json
    shell_json = os.path.join(home, ".config", "omarchy", "shell.json")
    if os.path.exists(shell_json):
        try:
            with open(shell_json, "r", encoding="utf-8") as f:
                sdata = json.load(f)
            # Find widgets list under bar
            bar_cfg = sdata.get("bar", {})
            widgets = bar_cfg.get("widgets", [])
            has_widget = any(isinstance(w, dict) and w.get("id") == "bobol.zapret" for w in widgets)
            if not has_widget:
                widgets.append({"id": "bobol.zapret"})
                bar_cfg["widgets"] = widgets
                sdata["bar"] = bar_cfg
                with open(shell_json, "w", encoding="utf-8") as f:
                    json.dump(sdata, f, indent=2, ensure_ascii=False)
                log("Виджет bobol.zapret добавлен в ~/.config/omarchy/shell.json", "✅")
        except Exception as e:
            log(f"Не удалось обновить shell.json: {e}", "⚠️")

    # Update ~/.bashrc with dynamic proxy hook if not present
    bashrc_path = os.path.join(home, ".bashrc")
    if os.path.exists(bashrc_path):
        with open(bashrc_path, "r", encoding="utf-8") as f:
            bashrc_content = f.read()

        hook_code = """
# Auto-configure proxy for terminal commands based on proxy state
_sync_proxy_state() {
    if (exec 3<>/dev/tcp/127.0.0.1/10809) 2>/dev/null; then
        exec 3>&-
        export http_proxy="http://127.0.0.1:10809"
        export https_proxy="http://127.0.0.1:10809"
        export all_proxy="socks5h://127.0.0.1:10808"
        export HTTP_PROXY="http://127.0.0.1:10809"
        export HTTPS_PROXY="http://127.0.0.1:10809"
        export ALL_PROXY="socks5h://127.0.0.1:10808"
    else
        unset http_proxy https_proxy all_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY
    fi
}
_sync_proxy_state
PROMPT_COMMAND="_sync_proxy_state${PROMPT_COMMAND:+;$PROMPT_COMMAND}"
"""
        if "_sync_proxy_state" not in bashrc_content:
            with open(bashrc_path, "a", encoding="utf-8") as f:
                f.write("\n" + hook_code.strip() + "\n")
            log("Добавлен динамический хук прокси в ~/.bashrc", "✅")

def main():
    parser = argparse.ArgumentParser(description="Omarchy VLESS Proxy Installer")
    parser.add_argument("-s", "--subscription", help="BeregVPN subscription URL or path to file", required=False)
    args = parser.parse_args()

    sub_input = args.subscription
    if not sub_input:
        if os.path.exists(os.path.join(ROOT_DIR, "subscription.txt")):
            sub_input = os.path.join(ROOT_DIR, "subscription.txt")
        else:
            print("Введите ссылку на подписку BeregVPN (или путь к файлу с vless://):")
            sub_input = input("URL/Путь: ").strip()

    if not sub_input:
        log("Не указана ссылка на подписку. Завершение работы.", "❌")
        sys.exit(1)

    ensure_dirs()
    sub_raw = fetch_subscription(sub_input)
    servers = process_subscription(sub_raw)
    if not servers:
        log("В предоставленной ссылке не найдено VLESS ключей!", "❌")
        sys.exit(1)

    ensure_xray_binary()
    install_system_components()

    # Build initial active_config.json
    log("Инициализация начальной конфигурации...", "⚙️")
    def_server = servers[0]["id"]
    for s in servers:
        if "finland" in s["id"].lower():
            def_server = s["id"]
            break

    manager_script = os.path.join(CORE_DIR, "manager.py")
    subprocess.run([sys.executable, manager_script, "build", def_server, "system"], check=True)

    log("\n=======================================================", "🎉")
    log("Установка успешно завершена!", "🚀")
    log(f"Начальный сервер: {def_server} | DNS: Системный")
    log("Управление через виджет на панели Omarchy:")
    log("  - ЛКМ: Включить / Выключить прокси")
    log("  - ПКМ: Открыть настройки (выбор Сервера и DNS: Comss, GeoHide и др.)")
    log("Консольные команды:")
    log("  - zapret-toggle   (переключить состояние)")
    log("  - zapret-settings (открыть меню настроек)")
    log("  - zapret-status   (проверить текущий статус)")
    log("=======================================================\n")

if __name__ == "__main__":
    main()
