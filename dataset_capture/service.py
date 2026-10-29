import hashlib
import json
import os
import re
import shutil
import threading
import time
import uuid
from pathlib import Path

from .camera import jpeg_bytes
from .measurement import digest_json, raw_display, raw_statistics

CAPTURE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,95}\Z")


class ConflictError(ValueError):
    pass


class CaptureService:
    def __init__(self, camera, output: Path, preview_fps=3):
        self.camera = camera
        self.output = Path(output)
        self.preview_fps = preview_fps
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.connected = False
        self.error = None
        self.latest = None
        self.latest_ns = None
        self.latest_frame = None
        self.preview_enabled = True
        self.setup = {}
        self.control_events = []
        self.series = {"state": "idle"}
        self.series_cancel = threading.Event()
        self.series_thread = None
        self.thread = None

    def start(self):
        self.output.mkdir(parents=True, exist_ok=True)
        if (self.output / ".setup.json").exists():
            self.setup = json.loads((self.output / ".setup.json").read_text())
        try:
            self.connect()
        except Exception:
            pass  # The panel remains available with an actionable camera error.
        self.thread = threading.Thread(target=self._preview, name="camera-preview", daemon=True)
        self.thread.start()

    def close(self):
        self.stop.set()
        self.series_cancel.set()
        if self.series_thread:
            self.series_thread.join(timeout=45)
        if self.thread:
            self.thread.join(timeout=45)
        with self.lock:
            self.camera.close()
            self.connected = False

    def connect(self):
        self.require_idle()
        with self.lock:
            self.require_idle()
            self.connected = False
            self.latest = self.latest_ns = None
            self.latest_frame = None
            try:
                self.camera.close()
                self.camera.open()
                self.connected, self.error = True, None
            except Exception as exc:
                self.error = str(exc)
                raise
            return self.status()

    def require_camera(self):
        if not self.connected:
            raise RuntimeError(self.error or "Camera disconnected")

    def status(self):
        return {"connected": self.connected, "error": self.error,
                    "camera": self.camera.identity if self.connected else None,
                    "preview_updated_utc_ns": self.latest_ns,
                    "free_bytes": shutil.disk_usage(self.output).free,
                    "output": str(self.output.resolve()), "trigger_mode": "Software / FrameStart",
                    "preview_enabled": self.preview_enabled, "series": dict(self.series), "measurement_units": "DN",
                    "absolute_radiance_calibrated": False}

    def require_idle(self):
        if self.series.get("state") == "running":
            raise ConflictError("A measurement series owns the camera; cancel or wait before changing controls.")

    def settings(self):
        with self.lock:
            self.require_camera()
            return self.camera.settings()

    def set_setting(self, key, value):
        self.require_idle()
        with self.lock:
            self.require_idle()
            self.require_camera()
            before = self.camera.settings().get(key, {}).get("value")
            result = self.camera.set_setting(key, value)
            self.control_events.append({"utc_ns": time.time_ns(), "feature": key,
                                        "requested": value, "before": before, "after": result.get(key, {}).get("value")})
            return result

    def measurement_state(self):
        self.require_idle()
        with self.lock:
            self.require_idle()
            self.require_camera()
            return self.camera.snapshot()

    def enable_chunks(self):
        self.require_idle()
        with self.lock:
            self.require_idle()
            self.require_camera()
            report = self.camera.enable_chunks()
            self.control_events.append({"utc_ns": time.time_ns(), "action": "enable_chunks", "report": report})
            return report

    def save_setup(self, setup):
        self.require_idle()
        with self.lock:
            self.require_idle()
            path = self.output / ".setup.json"
            self._write_json(path, setup)
            self.setup = setup
            return setup

    def raw_region(self, x, y, width, height):
        frame = self.latest_frame
        if frame is None:
            raise RuntimeError("No acquired frame is available")
        if x < 0 or y < 0 or width < 1 or height < 1 or width > 64 or height > 64:
            raise ValueError("Choose a positive region no larger than 64 × 64")
        if x + width > frame.array.shape[1] or y + height > frame.array.shape[0]:
            raise ValueError("Region falls outside the acquired image")
        return {"x": x, "y": y, "units": "DN", "values": frame.array[y:y+height, x:x+width].tolist(),
                "pixel_format": frame.metadata["pixel_format"], "frame": frame.metadata.get("block_id"),
                "statistics": raw_statistics(frame.array, frame.metadata["pixel_format"])}

    def raw_preview(self, black=0, white=None):
        frame = self.latest_frame
        if frame is None:
            raise RuntimeError("No acquired frame is available")
        return jpeg_bytes(raw_display(frame.array, frame.metadata["pixel_format"], black, white))

    def _preview(self):
        while not self.stop.is_set():
            with self.lock:
                if self.connected and self.preview_enabled:
                    try:
                        frame = self.camera.grab()
                        self.latest, self.latest_ns = frame.jpeg, time.time_ns()
                        self.latest_frame = frame
                        self.error = None
                    except Exception as exc:
                        self.error = str(exc)
                        self.connected = False
                        self.latest = None
            self.stop.wait(1 / self.preview_fps)

    def capture(self, capture_id, context, *, series_owned=False):
        if not CAPTURE_ID.fullmatch(capture_id):
            raise ValueError("Capture ID must contain 1–96 letters, digits, underscores or hyphens")
        request = {"capture_id": capture_id, "context": context}
        canonical = json.dumps(request, sort_keys=True, allow_nan=False, separators=(",", ":"))
        request_hash = hashlib.sha256(canonical.encode()).hexdigest()
        target = self.output / capture_id
        if not series_owned:
            self.require_idle()
        with self.lock:
            if not series_owned:
                self.require_idle()
            # Retrying an acknowledged or timed-out capture must not acquire a different frame.
            if target.exists():
                metadata = json.loads((target / "metadata.json").read_text())
                if metadata["request_sha256"] != request_hash:
                    raise ConflictError("Capture ID already belongs to different context")
                return {"replayed": True, **metadata}
            self.require_camera()
            try:
                frame = self.camera.grab(record=True)
            except Exception as exc:
                # A timeout may leave an exposure/result pending. Require reopening
                # before another request, rather than risking a stale queued frame.
                self.connected, self.error = False, str(exc)
                raise
            if frame.payload is None:
                raise RuntimeError("Archival acquisition did not provide an SDK payload")
            self.latest_frame = frame
            self.latest, self.latest_ns = frame.jpeg, time.time_ns()
            # The Basler native runtime must initialize before NumPy on Linux.
            import numpy as np

            # Leave headroom for array, preview and metadata; actual writes can still fail safely.
            if shutil.disk_usage(self.output).free < frame.array.nbytes + len(frame.payload or b"") + len(frame.jpeg or b"") + 16 * 1024 * 1024:
                raise RuntimeError("Insufficient disk space for capture")
            staging = self.output / f".partial-{uuid.uuid4().hex}"
            staging.mkdir()
            try:
                with (staging / "image.npy").open("wb") as handle:
                    np.save(handle, frame.array, allow_pickle=False)
                    handle.flush()
                    os.fsync(handle.fileno())
                if frame.payload is not None:
                    (staging / "payload.bin").write_bytes(frame.payload)
                if frame.jpeg is not None:
                    (staging / "preview.jpg").write_bytes(frame.jpeg)
                state = dict(frame.state or {})
                state["control_events_this_process"] = list(self.control_events)
                (staging / "camera-state.json").write_text(json.dumps(state, indent=2, allow_nan=False) + "\n")
                raw_preview_error = None
                try:
                    (staging / "raw-preview.jpg").write_bytes(jpeg_bytes(raw_display(frame.array, frame.metadata["pixel_format"])))
                except ValueError as exc:
                    raw_preview_error = str(exc)
                files = {}
                for path in staging.iterdir():
                    digest = hashlib.sha256()
                    with path.open("rb") as handle:
                        for block in iter(lambda: handle.read(1024 * 1024), b""):
                            digest.update(block)
                    files[path.name] = {"bytes": path.stat().st_size, "sha256": digest.hexdigest()}
                metadata = {"schema_version": 2, **request, "request_sha256": request_hash,
                            **frame.metadata, "shape": list(frame.array.shape), "dtype": str(frame.array.dtype),
                            "files": files, "setup": self.setup, "setup_sha256": digest_json(self.setup),
                            "statistics": raw_statistics(frame.array, frame.metadata["pixel_format"]),
                            "configuration_sha256": state.get("configuration_sha256"),
                            "raw_preview": {"black_dn": 0, "white_dn": code_limit_for_frame(frame), "error": raw_preview_error,
                                            "measurement_data": False, "pipeline": "fixed linear display window, thumbnail, JPEG; no demosaicing"},
                            "measurement_claim": {"units": "DN", "raw_sensor_verified": False, "absolute_radiance_calibrated": False}}
                (staging / "metadata.json").write_text(json.dumps(metadata, indent=2, allow_nan=False) + "\n")
                for path in staging.iterdir():
                    with path.open("rb") as handle:
                        os.fsync(handle.fileno())
                self._fsync_dir(staging)
                os.rename(staging, target)
                self._fsync_dir(self.output)
                return {"replayed": False, **metadata}
            finally:
                if staging.exists():
                    shutil.rmtree(staging)

    def start_series(self, plan):
        self.require_idle()
        series_id = plan["series_id"]
        if not CAPTURE_ID.fullmatch(series_id) or len(series_id) > 65:
            raise ValueError("Series ID must be safe and at most 65 characters")
        if plan["kind"] == "dark" and not plan.get("dark_occlusion_confirmed"):
            raise ValueError("Confirm the lens/sensor is fully occluded before a dark series")
        with self.lock:
            self.require_idle()
            self.require_camera()
            settings = self.camera.settings()
            for key in ("ExposureAuto", "GainAuto"):
                if key in settings and settings[key]["value"] != "Off":
                    raise ValueError(f"Disable {key} before a measurement series")
            exposure = settings.get("ExposureTime")
            if not exposure or not exposure["writable"]:
                raise ValueError("Manual exposure control is unavailable")
            for value in plan["exposures_us"]:
                if not exposure["min"] <= value <= exposure["max"]:
                    raise ValueError(f"Exposure {value} is outside the camera's reported range")
            # A series can span restarts only by explicit resubmission. Do not silently
            # resume with an altered setup or camera configuration.
            baseline = self.camera.snapshot()
            binding = {"plan": plan, "setup_sha256": digest_json(self.setup),
                       "configuration_sha256": baseline["configuration_sha256"]}
            folder = self.output / ".series"
            folder.mkdir(exist_ok=True)
            path = folder / f"{series_id}.json"
            if path.exists() and json.loads(path.read_text())["binding"] != binding:
                raise ConflictError("Series ID exists with a different plan, setup or starting configuration")
            self._write_json(path, {"binding": binding, "state": "running"})
            self.series_cancel.clear()
            self.series = {"state": "running", "series_id": series_id, "completed": 0,
                           "total": len(plan["exposures_us"]) * plan["repeats"], "error": None}
            self.series_thread = threading.Thread(target=self._run_series, args=(plan, binding, path, exposure["value"]), daemon=True)
            self.series_thread.start()
            return dict(self.series)

    def _run_series(self, plan, binding, path, original_exposure):
        terminal, error = "completed", None
        with self.lock:
            try:
                for i, exposure in enumerate(plan["exposures_us"]):
                    if self.series_cancel.is_set():
                        break
                    self.camera.set_setting("ExposureTime", exposure)
                    for _ in range(plan["settle_frames"]):
                        if self.series_cancel.is_set():
                            break
                        self.camera.grab()
                    for repeat in range(plan["repeats"]):
                        if self.series_cancel.is_set():
                            break
                        context = {**plan["context"], "measurement_kind": plan["kind"],
                                   "series": {"id": plan["series_id"], "exposure_index": i, "repeat": repeat,
                                              "requested_exposure_us": exposure, "binding": binding}}
                        capture_id = f"{plan['series_id']}-e{i:03d}-r{repeat:03d}"
                        self.capture(capture_id, context, series_owned=True)
                        self.series = {**self.series, "completed": self.series["completed"] + 1, "last_capture": capture_id}
                if self.series_cancel.is_set():
                    terminal = "cancelled"
            except Exception as exc:
                terminal, error = "failed", str(exc)
            finally:
                try:
                    self.camera.set_setting("ExposureTime", original_exposure)
                except Exception as exc:
                    terminal, error = "failed", f"Exposure restore failed: {exc}; prior error: {error}"
                self.series = {**self.series, "state": terminal, "error": error}
                try:
                    self._write_json(path, {"binding": binding, **self.series})
                except Exception as exc:
                    self.series = {**self.series, "state": "failed", "error": f"Series journal save failed: {exc}; prior error: {error}"}

    @classmethod
    def _write_json(cls, path, value):
        temp = path.parent / f".partial-{uuid.uuid4().hex}"
        try:
            with temp.open("w") as handle:
                handle.write(json.dumps(value, indent=2, allow_nan=False) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, path)
            cls._fsync_dir(path.parent)
        finally:
            temp.unlink(missing_ok=True)

    @staticmethod
    def _fsync_dir(path):
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def code_limit_for_frame(frame):
    from .measurement import code_limit
    return code_limit(frame.metadata["pixel_format"])
