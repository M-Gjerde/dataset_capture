"""Prepare or repair the desktop environment: python scripts/setup_env.py."""
import subprocess
import sys

from run import environment


def main():
    try:
        python = environment()
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"Setup stopped: {exc}", file=sys.stderr)
        return 1
    print(f"Ready: {python}")
    print("Next: python scripts/run.py --pi PI_IP  (or add --hotspot)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
