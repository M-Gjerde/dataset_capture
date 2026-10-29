import argparse
import asyncio
import socket
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Annotated, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .camera import BaslerCamera, SimulatedCamera
from .service import CaptureService, ConflictError

STATIC = Path(__file__).parent / "static"


class Setting(BaseModel):
    value: Any


class CaptureRequest(BaseModel):
    capture_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,95}$")
    context: dict[str, Any] = Field(default_factory=dict)


class PreviewControl(BaseModel):
    enabled: bool


class SeriesPlan(BaseModel):
    series_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,64}$")
    kind: Literal["dark", "flat", "linearity", "radiance_reference", "emitter", "scene", "validation"]
    exposures_us: list[Annotated[float, Field(gt=0, allow_inf_nan=False)]] = Field(min_length=1, max_length=30)
    repeats: int = Field(ge=1, le=100, default=2)
    settle_frames: int = Field(ge=0, le=10, default=1)
    dark_occlusion_confirmed: bool = False
    context: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def bound_count(self):
        if len(self.exposures_us) * self.repeats > 1000:
            raise ValueError("Limit a measurement series to 1000 saved frames")
        return self


def create_app(service):
    instance_id = str(uuid.uuid4())
    started = time.monotonic()
    @asynccontextmanager
    async def lifespan(app):
        await asyncio.to_thread(service.start)
        yield
        await asyncio.to_thread(service.close)

    app = FastAPI(title="Dataset Capture", lifespan=lifespan)
    # Access remotely through SSH forwarding; no unauthenticated LAN listener.
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]", "testserver"])

    @app.middleware("http")
    async def same_origin(request: Request, call_next):
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("origin")
            if origin and origin != str(request.base_url).rstrip("/"):
                return JSONResponse({"detail": "Cross-origin writes are disabled"}, status_code=403)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.exception_handler(ConflictError)
    async def conflict(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.exception_handler(ValueError)
    async def invalid(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=422)

    @app.exception_handler(RuntimeError)
    async def unavailable(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=503)

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    @app.get("/api/status")
    def status():
        return service.status()

    @app.get("/api/heartbeat")
    def heartbeat():
        # Never acquire the camera lock: long exposures must not look like Wi-Fi loss.
        return {"service": "dataset-capture", "instance_id": instance_id,
                "hostname": socket.gethostname(), "uptime_seconds": time.monotonic() - started,
                "utc_ns": time.time_ns(), "camera_connected": service.connected,
                "preview_updated_utc_ns": service.latest_ns,
                "series_state": service.series.get("state"), "simulated": isinstance(service.camera, SimulatedCamera)}

    @app.get("/api/connection")
    def local_connection():
        return {"mode": "direct", "state": "online", "message": "Direct connection to capture service",
                "pi": heartbeat(), "last_seen_seconds": 0, "latency_ms": None, "automatic_reconnect": False}

    @app.get("/api/protocol")
    def protocol():
        return FileResponse(Path(__file__).parent / "protocol.md", media_type="text/plain; charset=utf-8")

    @app.post("/api/connect")
    def connect():
        service.require_idle()
        try:
            return service.connect()
        except Exception as exc:
            raise HTTPException(503, str(exc)) from exc

    @app.get("/api/settings")
    def settings():
        return service.settings()

    @app.put("/api/settings/{name}")
    def set_setting(name: str, body: Setting):
        try:
            return service.set_setting(name, body.value)
        except (ValueError, RuntimeError):
            raise
        except Exception as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.post("/api/captures")
    def capture(body: CaptureRequest):
        return service.capture(body.capture_id, body.context)

    @app.get("/api/measurement-state")
    def measurement_state():
        return service.measurement_state()

    @app.post("/api/chunks/enable")
    def enable_chunks():
        return service.enable_chunks()

    @app.get("/api/setup")
    def setup():
        return service.setup

    @app.put("/api/setup")
    def save_setup(body: dict[str, Any]):
        return service.save_setup(body)

    @app.put("/api/preview")
    def preview_control(body: PreviewControl):
        service.preview_enabled = body.enabled
        return {"enabled": service.preview_enabled}

    @app.get("/api/raw")
    def raw(x: int = 0, y: int = 0, width: int = 8, height: int = 8):
        return service.raw_region(x, y, width, height)

    @app.get("/api/raw-preview.jpg")
    def raw_preview(black: float = 0, white: float | None = None):
        return Response(service.raw_preview(black, white), media_type="image/jpeg")

    @app.post("/api/series")
    def series(plan: SeriesPlan):
        return service.start_series(plan.model_dump())

    @app.get("/api/series")
    def series_status():
        return dict(service.series)

    @app.post("/api/series/cancel")
    def cancel_series():
        service.series_cancel.set()
        return {"cancel_requested": True, "note": "The current exposure/file write finishes before stopping."}

    @app.get("/api/preview.jpg")
    def preview():
        if service.latest is None:
            raise HTTPException(503, service.error or "Waiting for first frame")
        return Response(service.latest, media_type="image/jpeg")

    @app.get("/api/stream")
    async def stream(request: Request):
        async def frames():
            previous = None
            while not await request.is_disconnected():
                updated, jpeg = service.latest_ns, service.latest
                if jpeg is not None and updated != previous:
                    previous = updated
                    yield (b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                           + str(len(jpeg)).encode() + b"\r\n\r\n" + jpeg + b"\r\n")
                await asyncio.sleep(0.1)
        return StreamingResponse(frames(), media_type="multipart/x-mixed-replace; boundary=frame")

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app


def main():
    import uvicorn
    parser = argparse.ArgumentParser(description="Basler capture panel (use SSH forwarding for remote access)")
    parser.add_argument("--simulate", action="store_true")
    parser.add_argument("--serial")
    parser.add_argument("--output", type=Path, default=Path.home() / "captures")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--preview-fps", type=float, default=3)
    from .hotspot import add_hotspot_arguments, configure_hotspot
    add_hotspot_arguments(parser)
    args = parser.parse_args()
    if not 0 < args.preview_fps <= 15:
        parser.error("--preview-fps must be greater than zero and at most 15")
    configure_hotspot(args, parser)
    camera = SimulatedCamera() if args.simulate else BaslerCamera(args.serial)
    service = CaptureService(camera, args.output, args.preview_fps)
    uvicorn.run(create_app(service), host="127.0.0.1", port=args.port, workers=1, timeout_graceful_shutdown=5)


if __name__ == "__main__":
    main()
