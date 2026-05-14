#!/usr/bin/env python3
"""CLI tool for ZTE modem/router management (ZLT X25 PRO and compatible models).

Reverse-engineered from the ZTE web UI. Supports status, WiFi config,
device info, signal monitoring, and more.
"""

import argparse
import hashlib
import json
import random
import sys
import time
import urllib3

# Suppress InsecureRequestWarning for self-signed certs
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

try:
    import requests
except ImportError:
    print("Error: 'requests' package is required. Install with: pip install requests")
    sys.exit(1)


# --- API Command UUIDs (reverse-engineered from ZTE web UI) ---
CMD = {
    "pre_login": "3830c61a-620d-47da-ae47-33d8401401c4",
    "login": "d2aa9843-494b-4947-9621-a46ec652ecd9",
    "logout": "677d89ca-2e5c-4481-81e3-cb6965ae77da",
    "refresh_token": "f3b70f2f-8721-48c4-87ec-22d8c92dd3c9",
    "init_data": "9f2861ee-baf8-4038-bab6-774ad4e930b0",
    "device_info": "ece6b6d4-61c7-4dad-af23-c8249c75c58c",
    "loop_data": "2ee26212-96cc-45d3-8f0d-808e4cde884a",
    "signal_info": "7c6906a3-f7de-4795-a17e-ef032ffacda4",
    "connect_data": "b47e27c6-6faf-48ca-acb5-996cbef1ff56",
    "lan_config": "55f29f9b-20cd-4d72-ab20-63ba0b4d2a7a",
    "wifi_options": "e1f94523-e23d-476f-aa90-30d1cfafa2f9",
    "firmware_check": "e2e7ee8f-3f75-457a-8c18-bc2e726ffd04",
    "wifi_set": "03b3e808-47ea-4b37-b294-abfd12092d69",
    "apply": "06df6e71-3091-4fd3-98c4-759127d0f366",
}

# Authentication type mapping
AUTH_TYPES = {
    "0": "OPEN",
    "2": "WPA2-PSK",
    "3": "WPA/WPA2-PSK",
    "4": "WPA3-PSK",
    "5": "WPA2/WPA3-PSK",
}

ENCRYPTION_TYPES = {
    "0": "TKIP",
    "1": "AES",
    "2": "TKIP+AES",
}


class ZTEModem:
    """Client for ZTE modem API."""

    def __init__(self, host="192.168.100.1", scheme="https"):
        self.base_url = f"{scheme}://{host}/cgi-bin/http.cgi"
        self.session_id = self._generate_session_id()
        self.token = None
        self.session = requests.Session()
        self.session.verify = False
        self.session.headers.update({
            "Content-Type": "application/json; charset=UTF-8",
        })

    @staticmethod
    def _generate_session_id():
        part1 = hashlib.md5(str(random.random()).encode()).hexdigest()
        part2 = hashlib.md5(str(random.random()).encode()).hexdigest()
        return part1 + part2

    def _request(self, cmd, method="GET", extra=None):
        payload = {
            "cmd": cmd,
            "method": method,
            "sessionId": self.session_id,
        }
        if self.token:
            payload["token"] = self.token
        if extra:
            payload.update(extra)
        try:
            resp = self.session.post(self.base_url, json=payload, timeout=10)
            return resp.json()
        except requests.exceptions.ConnectionError:
            print(f"Error: Cannot connect to modem at {self.base_url}")
            sys.exit(1)
        except json.JSONDecodeError:
            print("Error: Invalid response from modem")
            sys.exit(1)

    def login(self, username, password):
        # Step 1: Get token
        pre = self._request(CMD["pre_login"])
        if not pre.get("success"):
            print("Error: Failed to get login token")
            return False
        token = pre["token"]

        # Step 2: Hash password: sha256(token + password)
        hashed = hashlib.sha256((token + password).encode()).hexdigest()

        # Step 3: Login
        result = self._request(CMD["login"], method="POST", extra={
            "username": username,
            "passwd": hashed,
            "token": token,
        })
        if result.get("success") and result.get("AUTH") == "AUTH":
            self.session_id = result["sessionId"]
            self.token = None  # Will refresh on next call
            self._refresh_token()
            return True

        if "login_fail" in str(result):
            print("Error: Invalid username or password")
        else:
            print(f"Error: Login failed: {result.get('message', 'unknown error')}")
        return False

    def _refresh_token(self):
        result = self._request(CMD["refresh_token"])
        if result.get("token"):
            self.token = result["token"]

    def logout(self):
        return self._request(CMD["logout"], method="POST")

    def get_device_info(self):
        return self._request(CMD["device_info"])

    def get_signal(self):
        return self._request(CMD["signal_info"])

    def get_loop_data(self):
        return self._request(CMD["loop_data"])

    def get_init_data(self):
        return self._request(CMD["init_data"])

    def get_lan_config(self):
        return self._request(CMD["lan_config"])

    def get_wifi_options(self):
        return self._request(CMD["wifi_options"])

    def get_firmware_info(self):
        return self._request(CMD["firmware_check"])

    def set_wifi(self, params):
        return self._request(CMD["wifi_set"], method="POST", extra=params)


# --- Output Formatting ---

def print_table(title, rows):
    if title:
        print(f"\n  {title}")
        print(f"  {'=' * len(title)}")
    if not rows:
        print("  (no data)")
        return
    max_key = max(len(str(r[0])) for r in rows)
    for key, val in rows:
        print(f"  {str(key):<{max_key + 2}} {val}")
    print()


def signal_bar(rsrp):
    """Convert RSRP to visual signal bar."""
    try:
        val = int(float(rsrp))
    except (ValueError, TypeError):
        return "?"
    if val >= -80:
        return "||||  Excellent"
    elif val >= -90:
        return "|||   Good"
    elif val >= -100:
        return "||    Fair"
    elif val >= -110:
        return "|     Poor"
    else:
        return ".     No signal"


def sinr_quality(sinr):
    try:
        val = float(sinr)
    except (ValueError, TypeError):
        return "?"
    if val >= 20:
        return "Excellent"
    elif val >= 13:
        return "Good"
    elif val >= 0:
        return "Fair"
    else:
        return "Poor"


def temp_status(temp):
    try:
        val = int(temp)
    except (ValueError, TypeError):
        return "?"
    if val >= 85:
        return f"{val}C  (!) HOT"
    elif val >= 70:
        return f"{val}C  Warm"
    else:
        return f"{val}C  OK"


def format_uptime(seconds):
    try:
        s = int(seconds)
    except (ValueError, TypeError):
        return seconds
    days, s = divmod(s, 86400)
    hours, s = divmod(s, 3600)
    mins, _ = divmod(s, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    parts.append(f"{mins}m")
    return " ".join(parts)


# --- Commands ---

def cmd_status(modem, args):
    """Show modem status overview."""
    info = modem.get_device_info()
    signal = modem.get_signal()
    loop = modem.get_loop_data()

    if not info.get("success"):
        print("Error: Not authenticated. Use: zte-cli login first")
        return

    print_table("Device", [
        ("Model", info.get("board_type", "?")),
        ("Real Device", info.get("real_device", "?")),
        ("Firmware", info.get("fake_version", "?")),
        ("IMEI", info.get("module_imei", "?")),
        ("SN", info.get("device_sn", "?")),
        ("Uptime", format_uptime(info.get("uptime", "?"))),
        ("Temperature", temp_status(info.get("device_temperature", "?"))),
        ("CPU Usage", f"{info.get('cpu_usage', '?')}%"),
        ("LAN MAC", info.get("lan_mac", "?")),
        ("LAN IP", info.get("lan_ip", "?")),
        ("WAN IP", signal.get("wan_ip", "?")),
        ("DNS", f"{signal.get('wan_dns', '')} / {signal.get('wan_dns2', '')}"),
    ])

    net_type = signal.get("network_type_str", loop.get("network_type_str", "?"))

    print_table("Network", [
        ("Type", net_type),
        ("Operator", loop.get("network_operator", "?")),
        ("SIM Status", "OK" if loop.get("sim_status") == "1" else "Error"),
        ("Roaming", "Yes" if loop.get("roam_status") == "1" else "No"),
    ])

    print_table("Signal - LTE", [
        ("RSRP", f"{signal.get('RSRP', '?')} dBm  {signal_bar(signal.get('RSRP'))}"),
        ("RSSI", f"{signal.get('RSSI', '?')} dBm"),
        ("SINR", f"{signal.get('SINR', '?')} dB  {sinr_quality(signal.get('SINR'))}"),
        ("RSRQ", f"{signal.get('RSRQ', '?')} dB"),
        ("PCI", signal.get("PCI", "?")),
        ("Bands", signal.get("currentband", "?")),
        ("Bandwidth", f"{signal.get('bandwidth', '?')} MHz"),
    ])

    if signal.get("RSRP_5G"):
        print_table("Signal - 5G NR", [
            ("RSRP", f"{signal.get('RSRP_5G', '?')} dBm  {signal_bar(signal.get('RSRP_5G'))}"),
            ("RSSI", f"{signal.get('RSSI_5G', '?')} dBm"),
            ("SINR", f"{signal.get('SINR_5G', '?')} dB  {sinr_quality(signal.get('SINR_5G'))}"),
            ("RSRQ", f"{signal.get('RSRQ_5G', '?')} dB"),
            ("PCI", signal.get("PCI_5G", "?")),
            ("Band", f"n{signal.get('currentband_5g', '?')}"),
            ("Bandwidth", f"{signal.get('bandwidth_5g', '?')} MHz"),
        ])

    wifi_2g = "ON" if loop.get("wlan2g_switch") == "1" else "OFF"
    wifi_5g = "ON" if loop.get("wlan5g_switch") == "1" else "OFF"
    wifi_6g = "ON" if loop.get("wlan6g_switch") == "1" else "OFF"

    print_table("WiFi", [
        ("2.4 GHz", f"{wifi_2g}  SSID: {loop.get('ssid2G', '?')}"),
        ("5 GHz", f"{wifi_5g}  SSID: {loop.get('ssid5G', '?')}"),
        ("6 GHz", f"{wifi_6g}  SSID: {loop.get('ssid6G', '?')}"),
    ])

    data_mb = float(loop.get("mon_download_flow", 0))
    if data_mb > 1024:
        data_str = f"{data_mb / 1024:.2f} GB"
    else:
        data_str = f"{data_mb:.2f} MB"
    print_table("Data Usage (this month)", [
        ("Download", data_str),
    ])


def cmd_signal(modem, args):
    """Show signal info (no auth required for basic info)."""
    signal = modem.get_signal()
    if not signal.get("success"):
        # Try without auth
        signal = modem._request(CMD["signal_info"])

    if not signal.get("success"):
        print("Error: Cannot get signal info")
        return

    print_table("Signal - LTE", [
        ("RSRP", f"{signal.get('RSRP', '?')} dBm  {signal_bar(signal.get('RSRP'))}"),
        ("RSSI", f"{signal.get('RSSI', '?')} dBm"),
        ("SINR", f"{signal.get('SINR', '?')} dB  {sinr_quality(signal.get('SINR'))}"),
        ("RSRQ", f"{signal.get('RSRQ', '?')} dB"),
        ("PCI", signal.get("PCI", "?")),
        ("Bands", signal.get("currentband", "?")),
        ("Bandwidth", f"{signal.get('bandwidth', '?')} MHz"),
        ("Frequency", signal.get("FREQ", "?")),
    ])

    if signal.get("RSRP_5G"):
        print_table("Signal - 5G NR", [
            ("RSRP", f"{signal.get('RSRP_5G', '?')} dBm  {signal_bar(signal.get('RSRP_5G'))}"),
            ("RSSI", f"{signal.get('RSSI_5G', '?')} dBm"),
            ("SINR", f"{signal.get('SINR_5G', '?')} dB  {sinr_quality(signal.get('SINR_5G'))}"),
            ("RSRQ", f"{signal.get('RSRQ_5G', '?')} dB"),
            ("PCI", signal.get("PCI_5G", "?")),
            ("Band", f"n{signal.get('currentband_5g', '?')}"),
            ("Bandwidth", f"{signal.get('bandwidth_5g', '?')} MHz"),
            ("Frequency", signal.get("FREQ_5G", "?")),
        ])

    print_table("Connection", [
        ("Network", signal.get("network_type_str", "?")),
        ("WAN IP", signal.get("wan_ip", "?")),
        ("Uptime", format_uptime(signal.get("uptime", "?"))),
    ])


def cmd_monitor(modem, args):
    """Live signal monitoring."""
    interval = args.interval
    print(f"Monitoring signal every {interval}s (Ctrl+C to stop)\n")

    try:
        while True:
            signal = modem.get_signal()
            if not signal.get("success"):
                print("Error: Cannot get signal info")
                time.sleep(interval)
                continue

            ts = time.strftime("%H:%M:%S")
            lte = f"LTE: RSRP={signal.get('RSRP','?')}  SINR={signal.get('SINR','?')}  Bands={signal.get('currentband','?')}"
            nr = ""
            if signal.get("RSRP_5G"):
                nr = f"  |  5G: RSRP={signal.get('RSRP_5G','?')}  SINR={signal.get('SINR_5G','?')}  Band=n{signal.get('currentband_5g','?')}"
            print(f"[{ts}] {lte}{nr}")
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nMonitoring stopped.")


def cmd_wifi(modem, args):
    """Show WiFi configuration."""
    lan = modem.get_lan_config()
    loop = modem.get_loop_data()

    if not lan.get("success"):
        print("Error: Not authenticated. Use: zte-cli login first")
        return

    auth_2g = AUTH_TYPES.get(lan.get("authenticationType_2g", ""), "?")
    auth_5g = AUTH_TYPES.get(lan.get("authenticationType_5g", ""), "?")

    print_table("WiFi - 2.4 GHz", [
        ("Status", "ON" if loop.get("wlan2g_switch") == "1" else "OFF"),
        ("SSID", loop.get("ssid2G", "?")),
        ("Security", auth_2g),
    ])

    print_table("WiFi - 5 GHz", [
        ("Status", "ON" if loop.get("wlan5g_switch") == "1" else "OFF"),
        ("SSID", loop.get("ssid5G", "?")),
        ("Security", auth_5g),
    ])

    if loop.get("wlan6g_switch"):
        print_table("WiFi - 6 GHz", [
            ("Status", "ON" if loop.get("wlan6g_switch") == "1" else "OFF"),
            ("SSID", loop.get("ssid6G", "?")),
        ])

    print_table("General", [
        ("Same SSID all bands", "Yes" if loop.get("wifiSames") == "1" else "No"),
        ("Mesh", "ON" if lan.get("mesh_switch") == "1" else "OFF"),
        ("IP Passthrough", "ON" if lan.get("ip_passthrough_sw") == "1" else "OFF"),
        ("LAN IP", lan.get("lanIp", "?")),
        ("Firewall", "ON" if lan.get("fw_switch") == "1" else "OFF"),
    ])


def cmd_info(modem, args):
    """Show device info."""
    info = modem.get_device_info()
    if not info.get("success"):
        print("Error: Not authenticated. Use: zte-cli login first")
        return

    eth_rates = info.get("eth_negotiation_rate", "")
    eth_parts = eth_rates.split(",") if eth_rates else []
    eth_display = ", ".join(f"LAN{i+1}: {r}Mbps" for i, r in enumerate(eth_parts))

    print_table("Device Info", [
        ("Model", info.get("board_type", "?")),
        ("Real Device", info.get("real_device", "?")),
        ("Firmware", info.get("fake_version", "?")),
        ("Hardware", info.get("hwversion", "?")),
        ("IMEI", info.get("module_imei", "?")),
        ("IMSI", info.get("IMSI", "?")),
        ("ICCID", info.get("ICCID", "?")),
        ("SN", info.get("device_sn", "?")),
        ("LAN MAC", info.get("lan_mac", "?")),
        ("LAN IP", info.get("lan_ip", "?")),
        ("Ethernet", eth_display),
        ("Uptime", format_uptime(info.get("uptime", "?"))),
        ("System Time", info.get("systime", "?")),
        ("Temperature", temp_status(info.get("device_temperature", "?"))),
        ("CPU Usage", f"{info.get('cpu_usage', '?')}%"),
        ("CPU Load", info.get("cpuload", "?")),
        ("Memory", info.get("memory", "?")),
        ("Flash", f"{info.get('flash_availeble', '?')} free / {info.get('flash_total', '?')} total"),
    ])


def cmd_firmware(modem, args):
    """Check firmware version."""
    fw = modem.get_firmware_info()
    print_table("Firmware", [
        ("Current", fw.get("fake_version", fw.get("real_fwversion", "?"))),
        ("Real", fw.get("real_fwversion", "?")),
        ("Update Available", "Yes" if fw.get("ver") else "No"),
    ])


def cmd_reboot(modem, args):
    """Reboot the modem."""
    if not args.yes:
        confirm = input("Reboot the modem? [y/N] ")
        if confirm.lower() != "y":
            print("Cancelled.")
            return
    result = modem._request(CMD["apply"], method="POST")
    if result.get("success"):
        print("Modem is rebooting...")
    else:
        print(f"Error: {result.get('message', 'unknown')}")


def cmd_raw(modem, args):
    """Send raw API command (for debugging)."""
    result = modem._request(args.uuid, method=args.method)
    print(json.dumps(result, indent=2))


def cmd_logout(modem, args):
    """Logout from the modem."""
    result = modem.logout()
    if result.get("success"):
        print("Logged out.")
    else:
        print(f"Logout failed: {result.get('message', '?')}")


# --- Main ---

def create_modem(args):
    modem = ZTEModem(host=args.host, scheme=args.scheme)
    if hasattr(args, "func") and args.func in (cmd_signal, cmd_firmware, cmd_raw):
        # These may work without auth
        if args.user and args.password:
            modem.login(args.user, args.password)
        return modem
    # All other commands need auth
    if not args.user or not args.password:
        print("Error: --user and --password are required")
        print("Usage: zte-cli --user admin --password YOUR_PASSWORD <command>")
        sys.exit(1)
    if not modem.login(args.user, args.password):
        sys.exit(1)
    return modem


def main():
    parser = argparse.ArgumentParser(
        prog="zte-cli",
        description="CLI for ZTE modem/router management (ZLT X25 PRO and compatible)",
    )
    parser.add_argument("--host", default="192.168.100.1", help="Modem IP (default: 192.168.100.1)")
    parser.add_argument("--scheme", default="https", choices=["http", "https"], help="Protocol (default: https)")
    parser.add_argument("--user", "-u", default="admin", help="Username (default: admin)")
    parser.add_argument("--password", "-p", help="Password")

    sub = parser.add_subparsers(dest="command", help="Command")

    sub.add_parser("status", help="Full status overview").set_defaults(func=cmd_status)
    sub.add_parser("signal", help="Signal strength info").set_defaults(func=cmd_signal)
    sub.add_parser("wifi", help="WiFi configuration").set_defaults(func=cmd_wifi)
    sub.add_parser("info", help="Device information").set_defaults(func=cmd_info)
    sub.add_parser("firmware", help="Firmware version check").set_defaults(func=cmd_firmware)
    sub.add_parser("logout", help="Logout session").set_defaults(func=cmd_logout)

    mon = sub.add_parser("monitor", help="Live signal monitoring")
    mon.add_argument("-i", "--interval", type=int, default=5, help="Refresh interval in seconds (default: 5)")
    mon.set_defaults(func=cmd_monitor)

    reb = sub.add_parser("reboot", help="Reboot the modem")
    reb.add_argument("-y", "--yes", action="store_true", help="Skip confirmation")
    reb.set_defaults(func=cmd_reboot)

    raw = sub.add_parser("raw", help="Send raw API command (debug)")
    raw.add_argument("uuid", help="Command UUID")
    raw.add_argument("-m", "--method", default="GET", choices=["GET", "POST"])
    raw.set_defaults(func=cmd_raw)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    modem = create_modem(args)
    args.func(modem, args)


if __name__ == "__main__":
    main()
