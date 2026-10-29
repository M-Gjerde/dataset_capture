"""Measurement evidence and display transforms; no inferred absolute calibration."""
import hashlib
import importlib.metadata
import json
import math
import platform
import re
from pathlib import Path


def digest_json(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def provenance():
    versions = {}
    for name in ("dataset-capture", "pypylon", "numpy", "Pillow", "fastapi", "uvicorn"):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    root = Path(__file__).parent
    sources = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
               for p in sorted(root.rglob("*")) if p.suffix in (".py", ".js", ".css", ".html")}
    return {"python": platform.python_version(), "platform": platform.platform(), "machine": platform.machine(),
            "packages": versions, "source_sha256": sources, "source_manifest_sha256": digest_json(sources)}


def code_limit(pixel_format):
    """Nominal output encoding limit, not measured sensor saturation or ADC depth."""
    match = re.fullmatch(r"(?:Mono|Bayer(?:RG|GR|GB|BG))(8|10|12|14|16)(?:p|Packed)?", pixel_format or "")
    return (1 << int(match.group(1))) - 1 if match else None


def raw_statistics(array, pixel_format):
    import numpy as np
    limit = code_limit(pixel_format)
    result = {"shape": list(array.shape), "dtype": str(array.dtype), "units": "DN",
              "nominal_code_max": limit, "sensor_saturation_dn": None,
              "min": int(array.min()), "max": int(array.max()), "mean": float(array.mean()),
              "zero_fraction": float(np.mean(array == 0)), "sample_count": int(array.size)}
    if limit is not None:
        result["at_or_above_code_max_fraction"] = float(np.mean(array >= limit))
        counts, edges = np.histogram(array, bins=64, range=(0, limit + 1))
        result["histogram"] = {"counts": counts.tolist(), "edges_dn": edges.tolist()}
        result["above_nominal_code_range"] = bool(array.max() > limit)
    if array.ndim == 2 and pixel_format.startswith("Bayer"):
        result["cfa_phases"] = {f"row{y}_col{x}": {"mean_dn": float(array[y::2, x::2].mean()),
                                "min_dn": int(array[y::2, x::2].min()), "max_dn": int(array[y::2, x::2].max())}
                               for y in range(min(2, array.shape[0])) for x in range(min(2, array.shape[1]))}
        result["cfa_note"] = "Phases are output-array coordinates. Confirm CFA orientation with ROI/mirroring on the real camera."
    return result


def raw_display(array, pixel_format, black=0.0, white=None):
    """Fixed linear DN window for display only. Never changes stored pixels."""
    import numpy as np
    if array.ndim != 2:
        raise ValueError("Raw mosaic view requires a single-plane Mono/Bayer array")
    if white is None:
        white = code_limit(pixel_format)
    if white is None or not math.isfinite(black) or not math.isfinite(white) or white <= black:
        raise ValueError("Set an explicit finite white level above the black level")
    return np.rint(np.clip((array.astype(np.float64) - black) / (white - black), 0, 1) * 255).astype(np.uint8)


def linear_signal(dn, dark_dn, relative_flat, exposure_s):
    """Affine signal normalization, DN/s. Inputs must be floating point arrays.

    No clipping, white balance, demosaicing, gamma or absolute-unit claim. The
    expression also preserves autodiff when passed differentiable array tensors.
    Caller must mask saturation/bad pixels and use positive flat/exposure values.
    """
    for value in (dn, dark_dn):
        dtype = getattr(value, "dtype", None)
        if dtype is not None and getattr(dtype, "kind", "f") not in ("f", "c"):
            raise ValueError("Convert DN and dark arrays to floating point before subtraction")
    return (dn - dark_dn) / (relative_flat * exposure_s)


def restore_dn(signal, dark_dn, relative_flat, exposure_s):
    """Algebraic inverse of linear_signal (up to floating point precision)."""
    return signal * relative_flat * exposure_s + dark_dn


def processing_audit(settings):
    """Conservative checks of observable controls; absence is never evidence of bypass."""
    checks = []
    def check(key, predicate, explanation):
        spec = settings.get(key)
        if not spec or spec.get("availability") != "readable":
            checks.append({"feature": key, "status": "unknown", "observed": None, "note": explanation})
        else:
            value = spec["value"]
            checks.append({"feature": key, "status": "observed_neutral" if predicate(value) else "review",
                           "observed": value, "note": explanation})
    for key in ("ExposureAuto", "GainAuto", "BalanceWhiteAuto", "BlackLevelAuto"):
        check(key, lambda v: v == "Off", "Automatic controls must be disabled or their absence documented for this model.")
    check("PixelFormat", lambda v: code_limit(str(v)) is not None,
          "Single-plane encoding is necessary, not proof of untouched sensor data; Mono output from a color sensor needs review.")
    for key in ("GammaEnable", "LUTEnable", "BslColorSpaceEnable", "ColorTransformationEnable"):
        check(key, lambda v: v is False, "Disabled readback is evidence for this exposed feature only.")
    if settings.get("GammaEnable", {}).get("value") is not False:
        check("Gamma", lambda v: v == 1, "Gamma 1 is neutral only if no additional color-space/tone operation is applied.")
    for key in ("DigitalShift", "NoiseReduction", "SharpnessEnhancement"):
        check(key, lambda v: v == 0, "Zero is a neutral candidate; model documentation must confirm the implementation.")
    for key in ("PgiMode", "BslBlackLevelCompensationMode", "BslShadingCorrectionMode", "BslDefectPixelCorrectionMode", "BslSpatialCorrectionMode", "BslHDRMode"):
        check(key, lambda v: v == "Off", "Unavailable controls may hide fixed processing; do not infer Off.")
    for key in ("BinningHorizontal", "BinningVertical", "DecimationHorizontal", "DecimationVertical"):
        check(key, lambda v: v == 1, "Combining or dropping samples changes the measurement geometry.")
    return {"raw_sensor_verified": False, "absolute_radiance_calibrated": False,
            "status": "model_and_measurement_validation_required", "checks": checks,
            "limitations": ["Hidden sensor/firmware processing is not established by GenICam readback.",
                            "A calibration reference and uncertainty budget are required for absolute units.",
                            "Black-level offset is recorded, not automatically set to zero: clipping dark noise loses information."]}
