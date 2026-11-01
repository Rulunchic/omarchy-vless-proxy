#!/usr/bin/env python3
"""
Subscription parser and updater for VLESS, VMess, Trojan protocols.
Supports standard Base64 subscriptions, Remnawave (with HWID and device headers),
and raw multi-line protocol links.
"""

import os
import sys
import json
import base64
import urllib.request
import urllib.parse
import re
import uuid

TRANSLIT_MAP = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo', 'ж': 'zh',
    'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm', 'н': 'n', 'о': 'o',
    'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u', 'ф': 'f', 'х': 'kh', 'ц': 'ts',
    'ч': 'ch', 'ш': 'sh', 'щ': 'shch', 'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya'
}

def transliterate(text):
    res = []
    for ch in text.lower():
        res.append(TRANSLIT_MAP.get(ch, ch))
    return "".join(res)

def sanitize_server_id(name, host, idx):
    t_name = transliterate(name)
    clean = re.sub(r'[^a-zA-Z0-9\s_-]', '', t_name).strip()
    slug = re.sub(r'[-\s]+', '_', clean).lower()
    if not slug or len(slug) < 2:
        host_slug = re.sub(r'[^a-zA-Z0-9]', '_', host.split('.')[0]).lower()
        slug = f"srv_{idx}_{host_slug}"
    return slug[:32].strip('_')

def get_hwid(base_dir=None):
    if base_dir:
        settings_file = os.path.join(base_dir, "settings.json")
        if os.path.exists(settings_file):
            try:
                with open(settings_file, "r", encoding="utf-8") as f:
                    s = json.load(f)
                    if s.get("hwid"):
                        return s["hwid"]
            except Exception:
                pass
    try:
        if os.path.exists("/etc/machine-id"):
            with open("/etc/machine-id", "r") as f:
                mid = f.read().strip()
                if mid and len(mid) == 32:
                    return str(uuid.UUID(mid))
    except Exception:
        pass
    return "99fa2ec2-fb25-4c7f-ae76-a6f6c2687259"

def fetch_subscription_text(url_or_text, hwid=None, base_dir=None):
    raw_str = url_or_text.strip()
    if not (raw_str.startswith("http://") or raw_str.startswith("https://")):
        return raw_str

    if not hwid:
        hwid = get_hwid(base_dir)

    user_agents = ["v2rayN", "Happ/3.6.0", "sing-box/1.9.0", "ClashMeta", "v2rayNG"]
    last_err = None
    decoded_text = ""

    for ua in user_agents:
        req = urllib.request.Request(raw_str, headers={
            "User-Agent": ua,
            "x-hwid": hwid,
            "x-device-os": "linux",
            "x-device-model": "Linux amd64"
        })
        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                content = resp.read()
                # Try base64 decoding
                try:
                    # Fix padding
                    pad = len(content) % 4
                    c_padded = content + (b'=' * (4 - pad) if pad else b'')
                    decoded = base64.b64decode(c_padded).decode('utf-8', errors='ignore')
                except Exception:
                    decoded = content.decode('utf-8', errors='ignore')

                if "App not supported" not in decoded and "Limit of devices reached" not in decoded and len(decoded.strip()) > 10:
                    decoded_text = decoded
                    break
                else:
                    decoded_text = decoded
        except Exception as e:
            last_err = e
            continue

    if not decoded_text and last_err:
        raise RuntimeError(f"Ошибка загрузки подписки: {last_err}")
    return decoded_text

def parse_vless(link):
    u = urllib.parse.urlparse(link)
    qs = dict(urllib.parse.parse_qsl(u.query))
    name = urllib.parse.unquote(u.fragment).strip() or u.hostname
    user_id = u.username
    host = u.hostname
    port = u.port or 443

    stream_type = qs.get("type", "tcp")
    security = qs.get("security", "none")

    outbound = {
        "protocol": "vless",
        "settings": {
            "vnext": [{
                "address": host,
                "port": port,
                "users": [{
                    "id": user_id,
                    "encryption": qs.get("encryption", "none"),
                    "flow": qs.get("flow", "")
                }]
            }]
        },
        "streamSettings": {
            "network": stream_type,
            "security": security
        },
        "tag": "proxy"
    }

    if security == "reality":
        outbound["streamSettings"]["realitySettings"] = {
            "show": False,
            "fingerprint": qs.get("fp", "chrome"),
            "serverName": qs.get("sni", host),
            "publicKey": qs.get("pbk", ""),
            "shortId": qs.get("sid", ""),
            "spiderX": qs.get("spx", "/")
        }
    elif security == "tls":
        outbound["streamSettings"]["tlsSettings"] = {
            "serverName": qs.get("sni", host),
            "allowInsecure": False
        }

    if stream_type == "ws":
        outbound["streamSettings"]["wsSettings"] = {
            "path": qs.get("path", "/"),
            "headers": {"Host": qs.get("host", host)}
        }
    elif stream_type in ["xhttp", "splithttp"]:
        outbound["streamSettings"]["network"] = "xhttp"
        outbound["streamSettings"]["xhttpSettings"] = {
            "path": qs.get("path", "/"),
            "mode": qs.get("mode", "packet-up")
        }
    elif stream_type == "grpc":
        outbound["streamSettings"]["grpcSettings"] = {
            "serviceName": qs.get("serviceName", "")
        }

    return name, host, outbound

def parse_trojan(link):
    u = urllib.parse.urlparse(link)
    qs = dict(urllib.parse.parse_qsl(u.query))
    name = urllib.parse.unquote(u.fragment).strip() or u.hostname
    password = u.username
    host = u.hostname
    port = u.port or 443
    stream_type = qs.get("type", "tcp")
    security = qs.get("security", "tls")

    outbound = {
        "protocol": "trojan",
        "settings": {
            "servers": [{
                "address": host,
                "port": port,
                "password": password
            }]
        },
        "streamSettings": {
            "network": stream_type,
            "security": security,
            "tlsSettings": {
                "serverName": qs.get("sni", host),
                "allowInsecure": False
            }
        },
        "tag": "proxy"
    }
    return name, host, outbound

def parse_vmess(link):
    data_b64 = link[8:]
    pad = len(data_b64) % 4
    if pad: data_b64 += '=' * (4 - pad)
    raw = base64.b64decode(data_b64).decode('utf-8', errors='ignore')
    v = json.loads(raw)
    name = v.get("ps", v.get("add"))
    host = v.get("add")
    port = int(v.get("port", 443))
    uid = v.get("id")
    net = v.get("net", "tcp")
    tls = v.get("tls", "")

    outbound = {
        "protocol": "vmess",
        "settings": {
            "vnext": [{
                "address": host,
                "port": port,
                "users": [{
                    "id": uid,
                    "alterId": int(v.get("aid", 0)),
                    "security": "auto"
                }]
            }]
        },
        "streamSettings": {
            "network": net,
            "security": "tls" if tls == "tls" else "none"
        },
        "tag": "proxy"
    }
    if tls == "tls":
        outbound["streamSettings"]["tlsSettings"] = {
            "serverName": v.get("sni", host),
            "allowInsecure": False
        }
    return name, host, outbound

def build_standalone_config(outbound):
    return {
        "log": {"loglevel": "warning"},
        "inbounds": [
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
        ],
        "outbounds": [
            outbound,
            {"protocol": "freedom", "tag": "direct"}
        ]
    }

def update_from_subscription(url_or_text, base_dir, hwid=None):
    """
    Fetches and parses links, writes individual configs to configs/,
    and writes servers.json.
    Returns list of dicts: [{"id": sid, "name": sname, "host": shost, "file": sfile}]
    """
    text = fetch_subscription_text(url_or_text, hwid, base_dir=base_dir)
    if "Limit of devices reached" in text and ("vless://" not in text or text.count("vless://") == 1):
        raise ValueError("Превышен лимит устройств на сервере подписки (Limit of devices reached). Сбросьте устройства в Telegram-боте.")

    configs_dir = os.path.join(base_dir, "configs")
    os.makedirs(configs_dir, exist_ok=True)
    servers_file = os.path.join(base_dir, "servers.json")

    parsed_servers = []
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    idx = 1
    seen_ids = set()
    for line in lines:
        try:
            if line.startswith("vless://"):
                sname, shost, sob = parse_vless(line)
            elif line.startswith("trojan://"):
                sname, shost, sob = parse_trojan(line)
            elif line.startswith("vmess://"):
                sname, shost, sob = parse_vmess(line)
            else:
                continue

            if "App not supported" in sname or "Limit of devices" in sname or shost == "0.0.0.0":
                continue

            sid = sanitize_server_id(sname, shost, idx)
            if sid in seen_ids:
                sid = f"{sid}_{idx}"
            seen_ids.add(sid)

            cfg_data = build_standalone_config(sob)
            sfile = f"{sid}.json"
            cfg_path = os.path.join(configs_dir, sfile)

            with open(cfg_path, "w", encoding="utf-8") as f:
                json.dump(cfg_data, f, indent=2, ensure_ascii=False)

            parsed_servers.append({
                "id": sid,
                "name": sname,
                "file": sfile,
                "host": shost
            })
            idx += 1
        except Exception as err:
            print(f"Предупреждение: пропуск некорректной ссылки {line[:30]}... ({err})", file=sys.stderr)

    if not parsed_servers:
        raise ValueError("Не найдено рабочих серверов в подписке.")

    with open(servers_file, "w", encoding="utf-8") as f:
        json.dump(parsed_servers, f, indent=2, ensure_ascii=False)

    return parsed_servers

if __name__ == "__main__":
    if len(sys.argv) > 1:
        u = sys.argv[1]
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        srvs = update_from_subscription(u, base)
        print(f"Успешно импортировано {len(srvs)} серверов:")
        for s in srvs:
            print(f" - [{s['id']}] {s['name']} ({s['host']})")
