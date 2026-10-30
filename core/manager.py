#!/usr/bin/env python3
import json
import os
import sys
import subprocess
import shutil

DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORE_DIR = os.path.join(DIR, "core")
CONFIGS_DIR = os.path.join(DIR, "configs")
SERVERS_FILE = os.path.join(DIR, "servers.json")
SETTINGS_FILE = os.path.join(DIR, "settings.json")
ACTIVE_CONFIG = os.path.join(DIR, "active_config.json")
PROXY_SCRIPT = os.path.join(CORE_DIR, "proxy.sh")

# DNS Profiles
DNS_PROVIDERS = [
    ("system", "Системный / Серверный (По умолчанию — самый быстрый)", {
        "servers": [],
        "hosts": {},
        "direct_ips": []
    }),
    ("comss", "Comss.one Smart DNS (ChatGPT, Claude, Discord)", {
        "servers": ["https://dns.comss.one/dns-query"],
        "hosts": {"dns.comss.one": "185.146.157.78"},
        "direct_ips": []
    }),
    ("geohide", "GeoHide Smart DNS (193.233.112.88)", {
        "servers": ["193.233.112.88"],
        "hosts": {},
        "direct_ips": ["193.233.112.88"]
    }),
    ("cloudflare", "Cloudflare DoH (1.1.1.1)", {
        "servers": ["https://1.1.1.1/dns-query"],
        "hosts": {},
        "direct_ips": []
    }),
    ("adguard", "AdGuard DoH (Блокировка рекламы)", {
        "servers": ["https://dns.adguard-dns.com/dns-query"],
        "hosts": {"dns.adguard-dns.com": "94.140.14.14"},
        "direct_ips": []
    }),
]

def load_servers():
    """Load server list from servers.json or scan configs directory."""
    if os.path.exists(SERVERS_FILE):
        try:
            with open(SERVERS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list) and len(data) > 0:
                    return [(s["id"], s["name"], s.get("file", f"{s['id']}.json")) for s in data]
        except Exception:
            pass

    # Fallback scan
    servers = []
    if os.path.exists(CONFIGS_DIR):
        for fname in sorted(os.listdir(CONFIGS_DIR)):
            if fname.endswith(".json") and fname != "active_config.json":
                sid = fname[:-5]
                name = sid.replace("_", " ").title()
                servers.append((sid, name, fname))
    return servers if servers else [("default", "Default Server", "default.json")]

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    servers = load_servers()
    def_server = servers[0][0] if servers else "default"
    # Prefer Finland or European if present
    for sid, name, _ in servers:
        if "finland" in sid.lower() or "финляндия" in name.lower():
            def_server = sid
            break
    return {"server": def_server, "dns": "system"}

def save_settings(settings):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)

def get_server_tuple(server_id):
    servers = load_servers()
    for sid, name, fn in servers:
        if sid == server_id:
            return sid, name, fn
    return servers[0] if servers else ("default", "Default", "default.json")

def get_dns_tuple(dns_id):
    for did, name, dinfo in DNS_PROVIDERS:
        if did == dns_id:
            return did, name, dinfo
    return DNS_PROVIDERS[0]

def build_active_config(server_id=None, dns_id=None):
    settings = load_settings()
    if server_id:
        settings["server"] = server_id
    if dns_id:
        settings["dns"] = dns_id

    sid, sname, sfile = get_server_tuple(settings.get("server"))
    did, dname, dinfo = get_dns_tuple(settings.get("dns", "system"))

    server_cfg_path = os.path.join(CONFIGS_DIR, sfile)
    if not os.path.exists(server_cfg_path):
        # Check root DIR as fallback
        server_cfg_path = os.path.join(DIR, sfile)

    if not os.path.exists(server_cfg_path):
        raise FileNotFoundError(f"Config file not found: {server_cfg_path}")

    with open(server_cfg_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    # Inbounds: SOCKS5 10808 and HTTP 10809
    cfg["inbounds"] = [
        {
            "tag": "socks",
            "listen": "127.0.0.1",
            "port": 10808,
            "protocol": "socks",
            "settings": {"auth": "noauth", "udp": True},
            "sniffing": {"enabled": True, "destOverride": ["http", "tls"]}
        },
        {
            "tag": "http",
            "listen": "127.0.0.1",
            "port": 10809,
            "protocol": "http"
        }
    ]

    # Tag outbounds
    if "outbounds" not in cfg or not cfg["outbounds"]:
        raise ValueError("Invalid configuration: no outbounds found")

    cfg["outbounds"][0]["tag"] = "proxy"
    if len(cfg["outbounds"]) > 1:
        cfg["outbounds"][1]["tag"] = "direct"
    else:
        cfg["outbounds"].append({"tag": "direct", "protocol": "freedom"})

    # Inject DNS configuration if specified
    if dinfo and dinfo.get("servers"):
        dns_block = {
            "servers": dinfo["servers"]
        }
        if dinfo.get("hosts"):
            dns_block["hosts"] = dinfo["hosts"]
        cfg["dns"] = dns_block

        rules = []
        if dinfo.get("direct_ips"):
            rules.append({
                "type": "field",
                "ip": dinfo["direct_ips"],
                "outboundTag": "direct"
            })
        rules.append({
            "type": "field",
            "inboundTag": ["socks", "http"],
            "outboundTag": "proxy"
        })
        cfg["routing"] = {
            "domainStrategy": "IPIfNonMatch",
            "rules": rules
        }
    else:
        cfg.pop("dns", None)
        cfg.pop("routing", None)

    with open(ACTIVE_CONFIG, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)

    save_settings(settings)
    return sid, sname, did, dname

def is_proxy_running():
    try:
        res = subprocess.run([PROXY_SCRIPT, "status"], capture_output=True, text=True)
        return "🟢" in res.stdout
    except Exception:
        return False

def apply_and_restart(server_id, dns_id):
    was_running = is_proxy_running()
    sid, sname, did, dname = build_active_config(server_id, dns_id)

    if was_running:
        subprocess.run([PROXY_SCRIPT, "restart"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Desktop notification
    notify_title = "Настройки прокси обновлены"
    status_str = " (Прокси перезапущен)" if was_running else " (Прокси выключен)"
    notify_body = f"Сервер: {sname}\nDNS: {dname}{status_str}"
    subprocess.run(["notify-send", "-a", "Proxy Manager", notify_title, notify_body], check=False)

def open_zenity_dialog():
    settings = load_settings()
    servers = load_servers()
    cur_server = settings.get("server")
    cur_dns = settings.get("dns", "system")

    # Order options with current selected first
    server_names_ordered = [name for sid, name, _ in servers if sid == cur_server] + \
                           [name for sid, name, _ in servers if sid != cur_server]

    dns_names_ordered = [name for did, name, _ in DNS_PROVIDERS if did == cur_dns] + \
                        [name for did, name, _ in DNS_PROVIDERS if did != cur_dns]

    cmd = [
        "zenity",
        "--forms",
        "--title=Настройки Прокси",
        "--text=Выберите сервер и DNS-сервер:",
        "--separator=|",
        "--add-combo=Сервер",
        f"--combo-values={'|'.join(server_names_ordered)}",
        "--add-combo=DNS-сервер",
        f"--combo-values={'|'.join(dns_names_ordered)}"
    ]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            return
        out = proc.stdout.strip()
        if not out:
            return
        parts = out.split("|")
        selected_server_name = parts[0] if len(parts) > 0 else ""
        selected_dns_name = parts[1] if len(parts) > 1 else ""

        target_server = cur_server
        for sid, name, _ in servers:
            if name == selected_server_name:
                target_server = sid
                break

        target_dns = cur_dns
        for did, name, _ in DNS_PROVIDERS:
            if name == selected_dns_name:
                target_dns = did
                break

        apply_and_restart(target_server, target_dns)
    except Exception as e:
        print(f"Error launching zenity: {e}", file=sys.stderr)
        open_tkinter_dialog()

def open_tkinter_dialog():
    try:
        import tkinter as tk
        from tkinter import ttk

        settings = load_settings()
        servers = load_servers()
        cur_server = settings.get("server")
        cur_dns = settings.get("dns", "system")

        root = tk.Tk()
        root.title("Настройки Прокси")
        root.geometry("440x240")
        root.resizable(False, False)

        tk.Label(root, text="Настройки прокси", font=("sans-serif", 13, "bold")).pack(pady=10)

        frame = tk.Frame(root)
        frame.pack(padx=20, fill="x")

        tk.Label(frame, text="Сервер:", anchor="w").grid(row=0, column=0, sticky="w", pady=5)
        server_var = tk.StringVar()
        server_combo = ttk.Combobox(frame, textvariable=server_var, state="readonly", width=34)
        server_combo['values'] = [name for _, name, _ in servers]
        for sid, name, _ in servers:
            if sid == cur_server:
                server_combo.set(name)
        server_combo.grid(row=0, column=1, pady=5)

        tk.Label(frame, text="DNS:", anchor="w").grid(row=1, column=0, sticky="w", pady=5)
        dns_var = tk.StringVar()
        dns_combo = ttk.Combobox(frame, textvariable=dns_var, state="readonly", width=34)
        dns_combo['values'] = [name for _, name, _ in DNS_PROVIDERS]
        for did, name, _ in DNS_PROVIDERS:
            if did == cur_dns:
                dns_combo.set(name)
        dns_combo.grid(row=1, column=1, pady=5)

        def on_save():
            s_name = server_var.get()
            d_name = dns_var.get()
            t_server = cur_server
            for sid, name, _ in servers:
                if name == s_name:
                    t_server = sid; break
            t_dns = cur_dns
            for did, name, _ in DNS_PROVIDERS:
                if name == d_name:
                    t_dns = did; break
            root.destroy()
            apply_and_restart(t_server, t_dns)

        btn_frame = tk.Frame(root)
        btn_frame.pack(pady=15)
        tk.Button(btn_frame, text="Применить", command=on_save, width=12, bg="#4caf50", fg="white").pack(side="left", padx=5)
        tk.Button(btn_frame, text="Отмена", command=root.destroy, width=12).pack(side="left", padx=5)

        root.mainloop()
    except Exception as err:
        print(f"Tkinter dialog error: {err}", file=sys.stderr)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "build":
            s = sys.argv[2] if len(sys.argv) > 2 else None
            d = sys.argv[3] if len(sys.argv) > 3 else None
            sid, sname, did, dname = build_active_config(s, d)
            print(f"Built active_config.json: Server={sname}, DNS={dname}")
        elif cmd == "gui":
            if shutil.which("zenity"):
                open_zenity_dialog()
            else:
                open_tkinter_dialog()
        elif cmd == "status":
            st = load_settings()
            sid, sname, _ = get_server_tuple(st.get("server"))
            did, dname, _ = get_dns_tuple(st.get("dns", "system"))
            print(json.dumps({
                "server_id": sid,
                "server_name": sname,
                "dns_id": did,
                "dns_name": dname,
                "running": is_proxy_running()
            }, ensure_ascii=False))
        elif cmd == "set":
            s = sys.argv[2] if len(sys.argv) > 2 else None
            d = sys.argv[3] if len(sys.argv) > 3 else "system"
            apply_and_restart(s, d)
    else:
        open_zenity_dialog()
