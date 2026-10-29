"""Optional host-side DatasetCapture hotspot (Windows or NetworkManager Linux)."""
import argparse
import platform
import shutil
import subprocess
from pathlib import Path

SSID = "DatasetCapture"
PASSWORD = "datasetcapture"
PROFILE_UUID = "5b78a193-087d-4a30-8650-45b657baba50"


class HotspotError(RuntimeError):
    pass


def _run(command):
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=90)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise HotspotError(f"Could not run {command[0]}: {exc}") from exc
    if result.returncode:
        raise HotspotError(
            (result.stderr or result.stdout).strip()
            or f"{command[0]} failed (exit {result.returncode})."
        )
    return result.stdout.strip()


def start_hotspot(interface=None):
    """Start only when explicitly requested; leave the hotspot on after app exit."""
    system = platform.system()
    if system == "Windows":
        if interface:
            raise HotspotError("--hotspot-interface is only supported on Linux.")
        powershell = shutil.which("powershell.exe")
        if not powershell:
            raise HotspotError("Windows PowerShell 5.1 is required to start Mobile hotspot.")
        _run([powershell, "-NoProfile", "-NonInteractive", "-File",
              str(Path(__file__).with_name("start_hotspot.ps1"))])
    elif system == "Linux":
        if not shutil.which("nmcli"):
            raise HotspotError("Install NetworkManager (nmcli) to use --hotspot.")
        devices = _run(["nmcli", "-t", "-f", "DEVICE,TYPE", "device", "status"])
        wifi = [line.rsplit(":", 1)[0] for line in devices.splitlines()
                if line.endswith(":wifi")]
        if interface is None:
            if len(wifi) != 1:
                raise HotspotError("Select a Wi-Fi adapter with --hotspot-interface NAME.")
            interface = wifi[0]
        if interface not in wifi:
            raise HotspotError(f"No managed Wi-Fi adapter named {interface}.")
        profiles = _run(["nmcli", "-g", "UUID", "connection", "show"]).splitlines()
        settings = [
            "connection.id", "dataset-capture-hotspot", "connection.autoconnect", "no",
            "connection.interface-name", interface,
            "802-11-wireless.ssid", SSID, "802-11-wireless.mode", "ap",
            "802-11-wireless.band", "bg",
            "802-11-wireless-security.key-mgmt", "wpa-psk",
            "802-11-wireless-security.proto", "rsn",
            "802-11-wireless-security.psk", PASSWORD,
            "ipv4.method", "shared", "ipv4.addresses", "10.42.0.1/24",
            "ipv6.method", "disabled",
        ]
        if PROFILE_UUID in profiles:
            _run(["nmcli", "connection", "modify", "uuid", PROFILE_UUID, *settings])
        else:
            _run(["nmcli", "connection", "add", "type", "wifi",
                  "connection.uuid", PROFILE_UUID, *settings])
        _run(["nmcli", "--wait", "30", "connection", "up", "uuid", PROFILE_UUID])
    else:
        raise HotspotError("--hotspot supports Windows and Linux with NetworkManager.")
    print(f"Hotspot {SSID} is ready. Connect the Pi, then use its assigned IP address.")


def add_hotspot_arguments(parser):
    parser.add_argument("--hotspot", action="store_true",
                        help="Start DatasetCapture Wi-Fi on this computer before the app")
    parser.add_argument("--hotspot-interface", help="Linux Wi-Fi adapter to use for --hotspot")


def configure_hotspot(args, parser):
    if args.hotspot_interface and not args.hotspot:
        parser.error("--hotspot-interface requires --hotspot")
    if args.hotspot:
        try:
            start_hotspot(args.hotspot_interface)
        except HotspotError as exc:
            parser.error(f"Hotspot could not start: {exc}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--interface", help="Linux Wi-Fi adapter")
    args = parser.parse_args()
    try:
        start_hotspot(args.interface)
    except HotspotError as exc:
        parser.exit(1, f"Hotspot could not start: {exc}\n")


if __name__ == "__main__":
    main()
