#!/usr/bin/env python3
"""
Hub Sync module for Omarchy VLESS Proxy.
Communicates with Bereg VPN Hub Server for dynamic subscription allocation and auto-rotation.
"""

import json
import logging
import os
import sys
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, Tuple

DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SETTINGS_FILE = os.path.join(DIR, "settings.json")
SERVERS_FILE = os.path.join(DIR, "servers.json")
CONFIGS_DIR = os.path.join(DIR, "configs")

logger = logging.getLogger("omarchy-hub-sync")


def get_or_create_client_id(settings: Dict) -> str:
    """Ensure client has a persistent UUID."""
    if settings.get("client_id"):
        return settings["client_id"]

    import uuid
    new_id = f"client_{uuid.uuid4().hex[:16]}"
    settings["client_id"] = new_id
    save_settings(settings)
    return new_id


def load_settings() -> Dict:
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_settings(settings: Dict) -> None:
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error("Failed to save settings: %s", e)


def fetch_subscription_from_hub(
    hub_url: str, client_id: str, client_name: str = "OmarchyUser", force_renew: bool = False
) -> Optional[Dict]:
    """Query Bereg VPN Hub server for subscription lease."""
    hub_url = hub_url.rstrip("/")
    params = {
        "client_id": client_id,
        "name": client_name,
        "force_renew": "true" if force_renew else "false",
    }
    url = f"{hub_url}/api/v1/subscription?{urllib.parse.urlencode(params)}"

    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "OmarchyVlessPlugin/1.0", "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=12) as resp:
            if resp.status == 200:
                return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        logger.error("Hub request failed (%s): %s", url, e)

    return None


def sync_hub_subscription(force_renew: bool = False) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Syncs with central Hub.
    Returns: (changed: bool, subscription_url: str, expires_at: str)
    """
    settings = load_settings()
    hub_url = settings.get("hub_url")
    if not hub_url:
        return False, None, None

    client_id = get_or_create_client_id(settings)
    client_name = settings.get("client_name", os.getenv("USER", "OmarchyUser"))

    data = fetch_subscription_from_hub(hub_url, client_id, client_name, force_renew=force_renew)
    if not data or not data.get("subscription_url"):
        return False, None, None

    new_sub_url = data["subscription_url"]
    new_expires_at = data.get("expires_at")
    old_sub_url = settings.get("subscription_url")

    changed = (new_sub_url != old_sub_url)

    # Save to settings
    settings["subscription_url"] = new_sub_url
    if new_expires_at:
        settings["subscription_expires_at"] = new_expires_at
    save_settings(settings)

    if changed or not os.path.exists(SERVERS_FILE):
        try:
            from subscription import update_from_subscription, get_hwid
        except ImportError:
            from core.subscription import update_from_subscription, get_hwid

        hwid = get_hwid(DIR)
        update_from_subscription(new_sub_url, DIR, hwid=hwid)

    return changed, new_sub_url, new_expires_at


def check_auto_rotation() -> Tuple[bool, Optional[str]]:
    """
    Checks if current subscription is expiring within 2 hours.
    If so, requests a forced renewal from the Hub.
    """
    settings = load_settings()
    if not settings.get("hub_url"):
        return False, None

    exp_str = settings.get("subscription_expires_at")
    should_renew = False

    if not exp_str or not settings.get("subscription_url"):
        should_renew = True
    else:
        try:
            # Parse ISO 8601 timestamp
            exp_clean = exp_str.replace("Z", "+00:00")
            exp_dt = datetime.fromisoformat(exp_clean)
            now = datetime.now(timezone.utc)
            if exp_dt - now < timedelta(hours=2):
                should_renew = True
        except Exception:
            should_renew = True

    if should_renew:
        changed, new_url, exp = sync_hub_subscription(force_renew=True)
        return changed, new_url

    return False, settings.get("subscription_url")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Omarchy Hub Sync CLI")
    parser.add_argument("--set-hub", help="Set Hub URL and sync")
    parser.add_argument("--check-rotate", action="store_true", help="Check expiry and rotate if needed")
    parser.add_argument("--force-renew", action="store_true", help="Force renew from Hub")
    args = parser.parse_args()

    s = load_settings()
    if args.set_hub:
        s["hub_url"] = args.set_hub.rstrip("/")
        save_settings(s)
        print(f"Hub URL set to: {s['hub_url']}")
        changed, url, exp = sync_hub_subscription(force_renew=True)
        print(f"Synced from Hub: {url} (expires: {exp}, changed={changed})")
    elif args.check_rotate:
        changed, url = check_auto_rotation()
        print(f"Auto-rotate check: changed={changed}, current_url={url}")
    elif args.force_renew:
        changed, url, exp = sync_hub_subscription(force_renew=True)
        print(f"Force renewed: {url} (expires: {exp})")
    else:
        changed, url, exp = sync_hub_subscription()
        print(f"Current Hub subscription: {url} (expires: {exp}, changed={changed})")
