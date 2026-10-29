"""Host capture requests and resumable pull of completed captures."""
import argparse
import hashlib
import json
import re
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path


def request_capture(url, capture_id, context, attempts=3):
    body = json.dumps({"capture_id": capture_id, "context": context}, allow_nan=False).encode()
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url.rstrip("/") + "/api/captures", data=body,
                                             headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.load(response)
        except urllib.error.HTTPError:
            raise  # Validation, hardware and ID conflicts need operator attention.
        except (urllib.error.URLError, TimeoutError):
            if attempt + 1 == attempts:
                raise
            time.sleep(1)


def verify_capture(directory):
    metadata = json.loads((directory / "metadata.json").read_text())
    if metadata.get("capture_id") != directory.name:
        raise ValueError(f"Capture ID mismatch: {directory}")
    files = metadata.get("files", {})
    if metadata.get("schema_version") not in (1, 2):
        raise ValueError(f"Unsupported capture schema: {directory}")
    allowed = {"image.npy", "preview.jpg", "raw-preview.jpg", "payload.bin", "camera-state.json"}
    required = {"image.npy", "preview.jpg"} if metadata.get("schema_version") == 1 else {"image.npy", "camera-state.json"}
    if not required <= set(files) or not set(files) <= allowed:
        raise ValueError(f"Unexpected capture files: {directory}")
    for name, expected in files.items():
        path = directory / name
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Missing or unsafe capture file: {path}")
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        if path.stat().st_size != expected["bytes"] or digest.hexdigest() != expected["sha256"]:
            raise ValueError(f"Checksum mismatch: {path}")
    if metadata.get("schema_version") == 2:
        if "payload.bin" not in files:
            raise ValueError(f"Missing archival payload: {directory}")
        if metadata.get("payload", {}).get("bytes") != files["payload.bin"]["bytes"]:
            raise ValueError(f"Payload length mismatch: {directory}")
    return metadata


def sync_captures(remote, source, destination):
    # These arguments become part of rsync's SSH command: deliberately limit syntax.
    if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*@[A-Za-z0-9][A-Za-z0-9.-]*", remote):
        raise ValueError("Remote must be user@hostname or user@IPv4-address")
    if not re.fullmatch(r"/[A-Za-z0-9_./-]+", source) or ".." in source.split("/"):
        raise ValueError("Source must be an absolute path with no spaces or parent traversal")
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    subprocess.run(["rsync", "-rt", "--checksum", "--partial-dir=.rsync-partial", "--delay-updates",
                    "--exclude=.partial-*", "--exclude=.rsync-partial", "-e", "ssh",
                    "--", f"{remote}:{source.rstrip('/')}/", str(destination) + "/"], check=True)
    verified = []
    for path in sorted(destination.iterdir()):
        if path.name.startswith("."):
            continue
        if not path.is_dir() or path.is_symlink():
            raise ValueError(f"Unexpected item in capture destination: {path}")
        verified.append(verify_capture(path)["capture_id"])
    return {"verified": verified, "destination": str(destination)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    capture = commands.add_parser("capture")
    capture.add_argument("capture_id")
    capture.add_argument("--url", default="http://127.0.0.1:8000")
    capture.add_argument("--context", type=Path, help="JSON object containing pose, lighting and session metadata")
    sync = commands.add_parser("sync")
    sync.add_argument("remote", help="user@pi-address")
    sync.add_argument("--source", default="/home/cameramodule/captures")
    sync.add_argument("--destination", type=Path, default=Path("captures"))
    args = parser.parse_args()
    if args.command == "capture":
        context = json.loads(args.context.read_text()) if args.context else {}
        result = request_capture(args.url, args.capture_id, context)
    else:
        result = sync_captures(args.remote, args.source, args.destination)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
