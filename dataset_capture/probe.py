"""Run on the Pi to inspect camera detection without changing camera settings."""
import json
import platform
import shutil
import sys


def main():
    report = {"platform": platform.platform(), "machine": platform.machine(),
              "python": sys.version, "libc": platform.libc_ver(),
              "disk_free_bytes": shutil.disk_usage(".").free}
    try:
        from pypylon import pylon
        report["cameras"] = [{"model": d.GetModelName(), "serial": d.GetSerialNumber(),
                              "transport": d.GetDeviceClass()}
                             for d in pylon.TlFactory.GetInstance().EnumerateDevices()]
    except Exception as exc:
        report["camera_error"] = str(exc)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
