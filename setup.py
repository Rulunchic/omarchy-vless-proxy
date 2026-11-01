#!/usr/bin/env python3
"""
Omarchy VLESS Proxy Setup & Installer
Parses any VLESS (Reality/XHTTP/WS/gRPC), VMess, Trojan, or Remnawave subscription,
downloads Xray binary, installs Omarchy bar widget, sets up smart application wrappers,
and configures proxy management.
"""

import os
import sys
import json
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
SETTINGS_JSON = os.path.join(ROOT_DIR, "settings.json")

if CORE_DIR not in sys.path:
    sys.path.insert(0, CORE_DIR)

from subscription import update_from_subscription, get_hwid

XRAY_RELEASE_URL = "https://github.com/XTLS/Xray-core/releases/download/v24.10.31/Xray-linux-64.zip"

def log(msg, symbol="ℹ️"):
    print(f"{symbol} {msg}")

def ensure_dirs():
    os.makedirs(CONFIGS_DIR, exist_ok=True)
    os.makedirs(BIN_DIR, exist_ok=True)
    os.makedirs(CORE_DIR, exist_ok=True)

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
    import urllib.request
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
    """Install bin wrappers, Omarchy plugin, application wrappers, and shell configs."""
    home = os.path.expanduser("~")
    user_bin = os.path.join(home, ".local", "bin")
    os.makedirs(user_bin, exist_ok=True)
    user_apps = os.path.join(home, ".local", "share", "applications")
    os.makedirs(user_apps, exist_ok=True)

    # 1. Make core scripts executable
    for f in ["proxy.sh", "sysproxy.sh"]:
        p = os.path.join(CORE_DIR, f)
        if os.path.exists(p):
            os.chmod(p, os.stat(p).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    # 2. Install CLI proxy wrappers into ~/.local/bin
    wrappers = ["zapret-toggle", "zapret-status", "zapret-settings"]
    for w in wrappers:
        src = os.path.join(ROOT_DIR, "bin", w)
        dst = os.path.join(user_bin, w)
        if os.path.exists(src):
            shutil.copy2(src, dst)
            os.chmod(dst, os.stat(dst).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            log(f"Установлен CLI скрипт: {dst}")

    # 3. Install Smart Application Wrappers
    # 3a. Chromium (Fix for Hyprland GSettings dynamic proxy switching)
    if shutil.which("chromium") or os.path.exists("/usr/bin/chromium"):
        src = os.path.join(ROOT_DIR, "bin", "chromium")
        dst = os.path.join(user_bin, "chromium")
        if os.path.exists(src):
            shutil.copy2(src, dst)
            os.chmod(dst, os.stat(dst).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            log(f"Установлен Chromium Wayland/GSettings wrapper: {dst}")

        # Update or create ~/.local/share/applications/chromium.desktop
        chrom_desktop = os.path.join(user_apps, "chromium.desktop")
        if not os.path.exists(chrom_desktop) and os.path.exists("/usr/share/applications/chromium.desktop"):
            shutil.copy2("/usr/share/applications/chromium.desktop", chrom_desktop)
        if os.path.exists(chrom_desktop):
            with open(chrom_desktop, "r", encoding="utf-8") as f:
                content = f.read()
            content = content.replace("Exec=/usr/bin/chromium", f"Exec={dst}")
            with open(chrom_desktop, "w", encoding="utf-8") as f:
                f.write(content)
            log("Настроен chromium.desktop с поддержкой динамического прокси")

    # 3b. T3 Code (CLI & GUI)
    if shutil.which("t3") or os.path.exists("/usr/bin/t3"):
        src = os.path.join(ROOT_DIR, "bin", "t3")
        dst = os.path.join(user_bin, "t3")
        if os.path.exists(src):
            shutil.copy2(src, dst)
            os.chmod(dst, os.stat(dst).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            log(f"Установлен T3 CLI wrapper: {dst}")

    if shutil.which("t3code") or os.path.exists("/usr/bin/t3code") or os.path.exists("/usr/lib/t3code/t3code"):
        src = os.path.join(ROOT_DIR, "bin", "t3code")
        dst = os.path.join(user_bin, "t3code")
        if os.path.exists(src):
            shutil.copy2(src, dst)
            os.chmod(dst, os.stat(dst).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            log(f"Установлен T3 Code GUI wrapper: {dst}")

    # 3c. Google Antigravity CLI (agy)
    target_agy = shutil.which("agy")
    if target_agy:
        # Check if agy in user_bin is binary (not script)
        bin_agy = os.path.join(user_bin, "agy")
        backup_bin = os.path.join(user_bin, "agy-bin")
        if os.path.exists(bin_agy) and not os.path.exists(backup_bin):
            with open(bin_agy, "rb") as f:
                header = f.read(4)
            if header == b"\x7fELF":
                shutil.move(bin_agy, backup_bin)
                log(f"Перемещен оригинальный agy бинарник в {backup_bin}")
        src = os.path.join(ROOT_DIR, "bin", "agy")
        if os.path.exists(src):
            shutil.copy2(src, bin_agy)
            os.chmod(bin_agy, os.stat(bin_agy).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            log(f"Установлен Antigravity agy CLI wrapper: {bin_agy}")

    # 3d. Antigravity IDE
    ide_found = False
    for p in [os.path.join(home, ".local", "opt", "antigravity-ide"), "/opt/antigravity-ide"]:
        if os.path.exists(p):
            ide_found = True
            break
    if ide_found or shutil.which("antigravity-ide"):
        src = os.path.join(ROOT_DIR, "bin", "antigravity-ide")
        dst = os.path.join(user_bin, "antigravity-ide")
        if os.path.exists(src):
            shutil.copy2(src, dst)
            os.chmod(dst, os.stat(dst).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            antigravity_link = os.path.join(user_bin, "antigravity")
            if not os.path.exists(antigravity_link):
                try:
                    os.symlink(dst, antigravity_link)
                except Exception:
                    pass
            log(f"Установлен Antigravity IDE wrapper: {dst}")

        # Update Antigravity IDE user settings
        ide_user_settings = os.path.join(home, ".config", "Antigravity IDE", "User", "settings.json")
        if os.path.exists(os.path.dirname(ide_user_settings)):
            try:
                cfg = {}
                if os.path.exists(ide_user_settings):
                    with open(ide_user_settings, "r", encoding="utf-8") as f:
                        cfg = json.load(f)
                cfg["http.proxy"] = "http://127.0.0.1:10809"
                cfg["http.proxySupport"] = "fallback"
                with open(ide_user_settings, "w", encoding="utf-8") as f:
                    json.dump(cfg, f, indent=4, ensure_ascii=False)
                log(f"Настроены прокси-параметры в {ide_user_settings}")
            except Exception as e:
                log(f"Не удалось настроить settings.json Antigravity IDE: {e}", "⚠️")

    # 4. Install Omarchy plugin
    plugin_dir = os.path.join(home, ".config", "omarchy", "plugins", "bobol.zapret")
    os.makedirs(plugin_dir, exist_ok=True)
    for f in ["manifest.json", "Zapret.qml"]:
        src = os.path.join(ROOT_DIR, "plugin", f)
        dst = os.path.join(plugin_dir, f)
        if os.path.exists(src):
            shutil.copy2(src, dst)
            log(f"Обновлен плагин Omarchy: {dst}")

    # 5. Ensure bobol.zapret is registered in ~/.config/omarchy/shell.json
    shell_json = os.path.join(home, ".config", "omarchy", "shell.json")
    if os.path.exists(shell_json):
        try:
            with open(shell_json, "r", encoding="utf-8") as f:
                sdata = json.load(f)
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

    # 6. Update ~/.bashrc with dynamic proxy hook if not present
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
    parser.add_argument("-s", "--subscription", help="Subscription URL or path to file", required=False)
    args = parser.parse_args()

    sub_input = args.subscription
    if not sub_input:
        if os.path.exists(os.path.join(ROOT_DIR, "subscription.txt")):
            sub_input = os.path.join(ROOT_DIR, "subscription.txt")
        else:
            print("Введите ссылку на подписку (VLESS, Remnawave, VMess, Trojan, BeregVPN и др.):")
            sub_input = input("URL/Путь: ").strip()

    if not sub_input:
        log("Не указана ссылка на подписку. Завершение работы.", "❌")
        sys.exit(1)

    ensure_dirs()
    log("Загрузка и парсинг серверов подписки...", "🔄")
    try:
        servers = update_from_subscription(sub_input, ROOT_DIR)
    except Exception as e:
        log(f"Ошибка обработки подписки: {e}", "❌")
        sys.exit(1)

    if not servers:
        log("В предоставленной ссылке не найдено рабочих ключей!", "❌")
        sys.exit(1)

    log(f"Успешно импортировано серверов: {len(servers)}", "✅")
    for s in servers:
        log(f" - [{s['id']}] {s['name']} ({s['host']})")

    ensure_xray_binary()
    install_system_components()

    # Determine default server (prefer Sweden, Finland, or European)
    def_server = servers[0]["id"]
    for s in servers:
        sid = s["id"].lower()
        if "sweden" in sid or "shvetsiya" in sid or "finland" in sid or "finlyandiya" in sid:
            def_server = s["id"]
            break

    # Save settings.json
    st = {
        "server": def_server,
        "dns": "system",
        "hwid": get_hwid(ROOT_DIR),
        "subscription_url": sub_input if sub_input.startswith("http") else ""
    }
    with open(SETTINGS_JSON, "w", encoding="utf-8") as f:
        json.dump(st, f, indent=2, ensure_ascii=False)

    # Build initial active_config.json
    log(f"Инициализация конфигурации с сервером '{def_server}'...", "⚙️")
    manager_script = os.path.join(CORE_DIR, "manager.py")
    subprocess.run([sys.executable, manager_script, "build", def_server, "system"], check=True)

    log("\n=======================================================", "🎉")
    log("Установка успешно завершена!", "🚀")
    log(f"Начальный сервер: {def_server} | DNS: Системный")
    log("Управление через виджет на панели Omarchy:")
    log("  - ЛКМ: Включить / Выключить прокси")
    log("  - ПКМ: Открыть настройки (выбор Сервера, DNS, смена подписки)")
    log("Консольные команды:")
    log("  - zapret-toggle   (переключить состояние)")
    log("  - zapret-settings (открыть меню настроек)")
    log("  - zapret-status   (проверить текущий статус)")
    log("  - core/proxy.sh sub [URL] (обновить серверы из подписки)")
    log("  - core/proxy.sh test (проверить соединение)")
    log("=======================================================\n")

if __name__ == "__main__":
    main()
