"""One-command desktop setup: python scripts/run.py --pi PI_IP [--hotspot]."""
import argparse
import hashlib
import ipaddress
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def run(command, **kwargs):
    subprocess.run([str(value) for value in command], check=True, **kwargs)


def environment():
    """Create or repair the local venv without requiring pip in the host Python."""
    if sys.version_info < (3, 10):
        raise RuntimeError("Install a full Python 3.10+ distribution, then retry.")
    target = ROOT / ".venv"
    python = target / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not python.exists():
        try:
            # Bootstrap pip separately so a failed ensurepip leaves a repairable venv.
            run([sys.executable, "-m", "venv", "--without-pip", target])
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(
                "Could not create .venv. On Ubuntu/Debian install python3-venv; "
                "on Windows repair Python and include pip/venv."
            ) from exc
    temporary = target / ".setup-tmp"
    temporary.mkdir(parents=True, exist_ok=True)
    setup_env = dict(os.environ, TMP=str(temporary), TEMP=str(temporary))
    probe = subprocess.run([str(python), "-m", "pip", "--version"],
                           capture_output=True, text=True, env=setup_env)
    repaired = probe.returncode != 0
    if repaired:
        print("Installing pip into .venv...", flush=True)
        result = subprocess.run([str(python), "-m", "ensurepip", "--upgrade"],
                                capture_output=True, text=True, env=setup_env)
        if result.returncode:
            detail = (result.stderr or result.stdout).strip()
            raise RuntimeError(
                "Could not bootstrap pip in .venv. On Ubuntu/Debian install "
                "python3-venv and python3-pip; on Windows repair the full Python "
                "installation with pip enabled, then rerun scripts/setup_env.py. "
                + detail
            )
        probe = subprocess.run([str(python), "-m", "pip", "--version"],
                               capture_output=True, text=True, env=setup_env)
        if probe.returncode:
            raise RuntimeError("pip is still unavailable in .venv after ensurepip; repair Python.")
    digest = hashlib.sha256((ROOT / "pyproject.toml").read_bytes()).hexdigest()
    stamp = target / ".desktop-requirements"
    packages = subprocess.run([str(python), "-c", "import fastapi, uvicorn, numpy, PIL"],
                              capture_output=True, env=setup_env)
    if repaired or packages.returncode or not stamp.exists() or stamp.read_text().strip() != digest:
        print("Installing desktop dependencies...", flush=True)
        run([python, "-m", "pip", "install", "-e", str(ROOT)], env=setup_env)
        stamp.write_text(digest)
    return python


def setup_ssh(address, username):
    """Use the terminal for passwords and first-use host-key verification."""
    if not shutil.which("ssh") or not shutil.which("ssh-keygen"):
        raise RuntimeError("Install OpenSSH Client (ssh and ssh-keygen), then retry.")
    target = f"{username}@{address}"
    options = ["-o", "ConnectTimeout=8", "-o", "StrictHostKeyChecking=ask"]
    dedicated = Path.home() / ".ssh" / "id_dataset_capture"
    identity = ["-i", str(dedicated)] if dedicated.exists() else []
    probe = subprocess.run(["ssh", *identity, "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
                            "-o", "ConnectTimeout=8", target, "true"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if probe.returncode == 0:
        return dedicated if identity else None
    print("First connection: verify the Pi host fingerprint and enter its login password.", flush=True)
    # A failed connection or changed host key stops here, before installing a key.
    run(["ssh", *options, target, "true"])
    ssh_dir = Path.home() / ".ssh"
    ssh_dir.mkdir(mode=0o700, exist_ok=True)
    key = ssh_dir / "id_dataset_capture"
    public = Path(str(key) + ".pub")
    if not key.exists() and not public.exists():
        run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", key])
    elif not key.exists() or not public.exists():
        raise RuntimeError(f"Incomplete SSH key pair at {key}; repair it before retrying.")
    public_key = Path(str(key) + ".pub").read_text().strip()
    quoted = shlex.quote(public_key)
    command = (
        "umask 077; mkdir -p ~/.ssh && touch ~/.ssh/authorized_keys && "
        f"{{ grep -qxF -- {quoted} ~/.ssh/authorized_keys || "
        f"printf '%s\\n' {quoted} >> ~/.ssh/authorized_keys; }}"
    )
    print("Authorize this PC's public key on the Pi (password may be requested again).", flush=True)
    run(["ssh", *options, target, command])
    # Explicit identity supports the dedicated key and passphrase-protected keys in ssh-agent.
    run(["ssh", "-i", key, "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
         "-o", "ConnectTimeout=8", target, "true"])
    return key


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pi", help="Pi IPv4 address; prompted if omitted")
    parser.add_argument("--username", default="cameramodule")
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--hotspot", action="store_true")
    parser.add_argument("--hotspot-interface", help="Linux Wi-Fi adapter")
    args = parser.parse_args()
    if sys.version_info < (3, 10):
        parser.error("Install Python 3.10 or newer.")
    if not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", args.username):
        parser.error("Invalid Pi username.")
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    if args.hotspot_interface and not args.hotspot:
        parser.error("--hotspot-interface requires --hotspot")
    try:
        python = environment()
        if args.hotspot:
            command = [python, "-m", "dataset_capture.hotspot"]
            if args.hotspot_interface:
                command += ["--interface", args.hotspot_interface]
            run(command, cwd=ROOT)
        address = args.pi or input("Connect the Pi to the same network. Pi IPv4 address: ").strip()
        parsed = ipaddress.IPv4Address(address)
        networks = ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
        if not any(parsed in ipaddress.IPv4Network(net) for net in networks):
            raise ValueError("Use the Pi's private LAN IPv4 address.")
        key = setup_ssh(str(parsed), args.username)
        command = [python, "-m", "dataset_capture.desktop", "--pi", str(parsed),
                   "--username", args.username, "--port", str(args.port), "--open-browser",
                   "--connect"]
        if key:
            command += ["--identity", str(key)]
        run(command, cwd=ROOT)
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"Setup stopped: {exc}\n")
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
