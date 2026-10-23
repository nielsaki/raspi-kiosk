#!/usr/bin/env python3
"""Kiosk launcher: a tiny local web server that Chromium shows at boot.

Serves the menu (web/index.html) and a small JSON API for checking the
internet connection, joining Wi-Fi networks via nmcli and remembering the
last choice. Standard library only, so nothing needs to be pip-installed.

Test on a computer without nmcli:  KIOSK_FAKE_WIFI=1 python3 launcher.py
"""
import json
import os
import signal
import socket
import subprocess
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
INDEX_FILE = HERE / "web" / "index.html"
CONFIG_FILE = Path(os.environ.get("KIOSK_CONFIG", HERE / "sites.json"))
STATE_FILE = Path(os.environ.get("KIOSK_STATE", Path.home() / ".local/state/kiosk/state.json"))
PORT = int(os.environ.get("KIOSK_PORT", "8765"))
FAKE_WIFI = os.environ.get("KIOSK_FAKE_WIFI") == "1"
PARENT_PID = os.environ.get("KIOSK_PARENT_PID")  # set by start-kiosk.sh
RECENT_HOSTS = 6

_fake = {"online": False, "ssid": None}
# The network someone confirmed on screen. Kept in memory, so the question comes once per kiosk start.
_confirmed = {"set": False, "network": None}


# --- Internet check ---------------------------------------------------------

def is_online():
    if FAKE_WIFI:
        return _fake["online"]
    try:
        # A captive portal answers with its own page instead of 204, which counts as offline.
        with urllib.request.urlopen("http://connectivitycheck.gstatic.com/generate_204", timeout=3) as r:
            return r.status == 204
    except Exception:
        pass
    for host, port in (("1.1.1.1", 443), ("8.8.8.8", 53)):
        try:
            socket.create_connection((host, port), timeout=2).close()
            return True
        except OSError:
            continue
    return False


def uptime():
    try:
        return float(Path("/proc/uptime").read_text().split()[0])
    except (OSError, ValueError):
        return None


def status():
    network = current_network()
    confirmed = _confirmed["set"] and _confirmed["network"] == network
    return {"online": is_online(), "network": network, "uptime": uptime(), "confirmed": confirmed}


def confirm_network(body):
    _confirmed.update(set=True, network=body.get("network"))
    return {"ok": True}


# --- Wi-Fi via NetworkManager -----------------------------------------------

def nmcli(*args, timeout=15):
    cmd = ["nmcli", *args]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        raise RuntimeError("nmcli findes ikke (kræver NetworkManager)")
    except subprocess.TimeoutExpired:
        raise RuntimeError("nmcli svarede ikke i tide")
    out = (r.stdout + r.stderr).lower()
    if r.returncode != 0 and ("authoriz" in out or "privilege" in out):
        # Normally covered by the polkit rule from install.sh; Pi OS also allows passwordless sudo.
        r = subprocess.run(["sudo", "-n", *cmd], capture_output=True, text=True, timeout=timeout)
    return r


def split_terse(line):
    """Split one line of `nmcli -t` output, where ':' inside values is escaped as '\\:'."""
    fields, cur, escaped = [], [], False
    for ch in line:
        if escaped:
            cur.append(ch)
            escaped = False
        elif ch == "\\":
            escaped = True
        elif ch == ":":
            fields.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    fields.append("".join(cur))
    return fields


def current_network():
    if FAKE_WIFI:
        return _fake["ssid"]
    try:
        r = nmcli("-t", "-f", "IN-USE,SSID", "device", "wifi", "list", "--rescan", "no", timeout=5)
        for line in r.stdout.splitlines():
            in_use, ssid = (split_terse(line) + [""])[:2]
            if in_use.strip() == "*" and ssid:
                return ssid
        r = nmcli("-t", "-f", "TYPE,STATE", "device", timeout=5)
        if any(line.startswith("ethernet:connected") for line in r.stdout.splitlines()):
            return "Kabel"
    except RuntimeError:
        pass
    return None


def wifi_scan():
    if FAKE_WIFI:
        time.sleep(1)
        nets = [("Hjemme", 82, True), ("Hallen_Gæst", 64, False), ("FSS", 47, True), ("Nabo 5G", 21, True)]
        return {"networks": [{"ssid": s, "signal": g, "secure": sec, "active": s == _fake["ssid"]}
                             for s, g, sec in nets]}
    fields = ("-t", "-f", "IN-USE,SSID,SIGNAL,SECURITY", "device", "wifi", "list")
    r = nmcli(*fields, "--rescan", "yes", timeout=30)
    if r.returncode != 0:
        # NetworkManager refuses a rescan right after another one; use the cached list instead.
        r = nmcli(*fields, "--rescan", "auto", timeout=30)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or "Kunne ikke søge efter netværk")

    best = {}
    for line in r.stdout.splitlines():
        parts = split_terse(line)
        if len(parts) < 4 or not parts[1]:
            continue  # hidden networks have no SSID
        in_use, ssid, signal, security = parts[:4]
        net = {
            "ssid": ssid,
            "signal": int(signal) if signal.isdigit() else 0,
            "secure": security.strip() not in ("", "--"),
            "active": in_use.strip() == "*",
        }
        old = best.get(ssid)
        if old:
            net["active"] = net["active"] or old["active"]
            net["signal"] = max(net["signal"], old["signal"])
        best[ssid] = net
    return {"networks": sorted(best.values(), key=lambda n: (not n["active"], -n["signal"]))}


def wifi_connect(body):
    ssid = str(body.get("ssid") or "").strip()
    password = str(body.get("password") or "")
    if not ssid:
        raise ValueError("Mangler netværksnavn")
    if FAKE_WIFI:
        time.sleep(2)
        if password == "forkert":
            raise RuntimeError("Forkert adgangskode")
        _fake.update(online=True, ssid=ssid)
        return {"ok": True}

    if password:
        # An old profile with a wrong password would otherwise be reused.
        nmcli("connection", "delete", "id", ssid, timeout=10)
    args = ["--wait", "30", "device", "wifi", "connect", ssid]
    if password:
        args += ["password", password]
    if body.get("hidden"):
        args += ["hidden", "yes"]
    r = nmcli(*args, timeout=45)
    if r.returncode != 0:
        msg = (r.stderr or r.stdout).strip().removeprefix("Error: ")
        raise RuntimeError(msg or "Kunne ikke forbinde")
    return {"ok": True}


# --- Sites config and remembered choices ------------------------------------

def load_config():
    try:
        raw = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise RuntimeError(f"Finder ikke {CONFIG_FILE}")
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Fejl i {CONFIG_FILE.name}, linje {e.lineno}, kolonne {e.colno}: {e.msg}")

    sites = []
    for i, s in enumerate(raw.get("sites", [])):
        pages = s.get("pages") or {}
        if isinstance(pages, dict):
            pages = [{"name": k, "path": v} for k, v in pages.items()]
        sites.append({
            "id": str(i),
            "name": s.get("name") or f"Side {i + 1}",
            "url": str(s.get("url") or "").rstrip("/"),
            "allow_other_address": bool(s.get("allow_other_address")),
            "pages": pages,
        })
    return {"title": raw.get("title") or "Vælg skærm", "sites": sites}


def load_state():
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def update_state(body):
    state = load_state()
    if isinstance(body.get("last"), dict):
        state["last"] = {"url": str(body["last"].get("url", "")), "label": str(body["last"].get("label", ""))}
    host = body.get("host")
    if isinstance(host, dict) and host.get("site") is not None and host.get("value"):
        hosts = state.setdefault("hosts", {})
        recent = [h for h in hosts.get(str(host["site"]), []) if h != host["value"]]
        hosts[str(host["site"])] = [str(host["value"])] + recent[:RECENT_HOSTS - 1]
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(STATE_FILE)
    return state


def quit_kiosk(body):
    if not PARENT_PID:
        return {"stopped": False}  # started by hand, nothing to stop
    # start-kiosk.sh closes Chromium and this server when it gets SIGTERM; wait so the reply gets out first.
    threading.Timer(0.5, os.kill, (int(PARENT_PID), signal.SIGTERM)).start()
    return {"stopped": True}


# --- HTTP -------------------------------------------------------------------

GET_ROUTES = {
    "/api/status": status,
    "/api/config": load_config,
    "/api/state": load_state,
    "/api/wifi/scan": wifi_scan,
}
POST_ROUTES = {
    "/api/wifi/connect": wifi_connect,
    "/api/wifi/confirm": confirm_network,
    "/api/state": update_state,
    "/api/quit": quit_kiosk,
}
ALLOWED_HOSTS = {f"127.0.0.1:{PORT}", f"localhost:{PORT}"}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def send_body(self, body, content_type, code=200):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, data, code=200):
        self.send_body(json.dumps(data, ensure_ascii=False).encode(), "application/json; charset=utf-8", code)

    def call(self, fn, *args):
        try:
            self.send_json(fn(*args))
        except Exception as e:
            self.send_json({"error": str(e)}, 500)

    def path_only(self):
        return self.path.split("?", 1)[0]

    def do_GET(self):
        path = self.path_only()
        if path in GET_ROUTES:
            return self.call(GET_ROUTES[path])
        if path in ("/", "/index.html"):
            return self.send_body(INDEX_FILE.read_bytes(), "text/html; charset=utf-8")
        self.send_json({"error": "Ikke fundet"}, 404)

    def do_POST(self):
        # Websites opened in the kiosk must not be able to change Wi-Fi: only accept JSON
        # (forces a CORS preflight we never approve) sent to our own host name.
        if self.headers.get("Host") not in ALLOWED_HOSTS or \
                not (self.headers.get("Content-Type") or "").startswith("application/json"):
            return self.send_json({"error": "Afvist"}, 403)
        fn = POST_ROUTES.get(self.path_only())
        if not fn:
            return self.send_json({"error": "Ikke fundet"}, 404)
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        except ValueError:
            return self.send_json({"error": "Ugyldig JSON"}, 400)
        self.call(fn, body)


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Kiosk launcher on http://127.0.0.1:{PORT}/" + ("  (fake Wi-Fi)" if FAKE_WIFI else ""), flush=True)
    server.serve_forever()
