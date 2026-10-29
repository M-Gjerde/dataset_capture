"""One camera owner; all calls are serialized by CaptureService."""
from __future__ import annotations

import io
import math
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from PIL import Image
from .measurement import code_limit, digest_json, processing_audit, provenance, raw_display

if TYPE_CHECKING:
    import numpy as np


@dataclass
class Frame:
    array: np.ndarray
    jpeg: bytes | None
    metadata: dict
    payload: bytes | None = None
    state: dict | None = None


def jpeg_bytes(rgb):
    image = Image.fromarray(rgb)
    image.thumbnail((1280, 960))
    output = io.BytesIO()
    image.save(output, format="JPEG", quality=80)
    return output.getvalue()


# Model-specific feature aliases. Bounds and choices come from the connected device.
FEATURES = {
    "ExposureAuto": (("ExposureAuto",), "enum"),
    "ExposureTime": (("ExposureTime", "ExposureTimeAbs"), "float"),
    "GainAuto": (("GainAuto",), "enum"),
    "Gain": (("Gain", "GainRaw"), "number"),
    "BalanceWhiteAuto": (("BalanceWhiteAuto",), "enum"),
    "GammaEnable": (("GammaEnable",), "bool"),
    "Gamma": (("Gamma",), "float"),
    "PixelFormat": (("PixelFormat",), "enum"),
    "OffsetX": (("OffsetX",), "int"),
    "OffsetY": (("OffsetY",), "int"),
    "Width": (("Width",), "int"),
    "Height": (("Height",), "int"),
    "ReverseX": (("ReverseX",), "bool"),
    "ReverseY": (("ReverseY",), "bool"),
}

# Explicit feature allowlist. The audit records unavailable entries instead of
# interpreting missing controls as disabled processing. Model-specific aliases
# are resolved to the actual node name in each saved snapshot.
FEATURES.update({
    "GainSelector": (("GainSelector",), "enum"),
    "BlackLevelSelector": (("BlackLevelSelector",), "enum"),
    "BlackLevel": (("BlackLevel", "BlackLevelRaw"), "number"),
    "BlackLevelAuto": (("BlackLevelAuto",), "enum"),
    "BslBlackLevelCompensationMode": (("BslBlackLevelCompensationMode",), "enum"),
    "BalanceRatioSelector": (("BalanceRatioSelector",), "enum"),
    "BalanceRatio": (("BalanceRatio", "BalanceRatioAbs"), "float"),
    "GammaSelector": (("GammaSelector",), "enum"),
    "DigitalShift": (("DigitalShift",), "int"),
    "SensorBitDepth": (("SensorBitDepth", "BslSensorBitDepth"), "enum"),
    "BslSensorBitDepthMode": (("BslSensorBitDepthMode",), "enum"),
    "TransferBitDepth": (("TransferBitDepth", "BslTransferBitDepth"), "enum"),
    "PixelColorFilter": (("PixelColorFilter",), "enum"),
    "LUTEnable": (("LUTEnable",), "bool"),
    "LUTSelector": (("LUTSelector",), "enum"),
    "PgiMode": (("PgiMode",), "enum"),
    "DemosaicingMode": (("DemosaicingMode", "BslDemosaicingMode"), "enum"),
    "NoiseReduction": (("NoiseReduction", "BslNoiseReduction"), "float"),
    "SharpnessEnhancement": (("SharpnessEnhancement", "BslSharpnessEnhancement"), "float"),
    "BslColorSpaceEnable": (("BslColorSpaceEnable",), "bool"),
    "BslColorSpace": (("BslColorSpace",), "enum"),
    "ColorTransformationSelector": (("ColorTransformationSelector",), "enum"),
    "ColorTransformationEnable": (("ColorTransformationEnable",), "bool"),
    "ColorTransformationValueSelector": (("ColorTransformationValueSelector",), "enum"),
    "ColorTransformationValue": (("ColorTransformationValue",), "float"),
    "BslShadingCorrectionMode": (("BslShadingCorrectionMode", "ShadingCorrectionMode"), "enum"),
    "BslDefectPixelCorrectionMode": (("BslDefectPixelCorrectionMode",), "enum"),
    "BslSpatialCorrectionMode": (("BslSpatialCorrectionMode",), "enum"),
    "BslHDRMode": (("BslHDRMode",), "enum"),
    "BslContrastMode": (("BslContrastMode",), "enum"),
    "BslBrightness": (("BslBrightness",), "float"),
    "BslContrast": (("BslContrast",), "float"),
    "BinningSelector": (("BinningSelector",), "enum"),
    "BinningHorizontal": (("BinningHorizontal",), "int"),
    "BinningVertical": (("BinningVertical",), "int"),
    "BinningHorizontalMode": (("BinningHorizontalMode",), "enum"),
    "BinningVerticalMode": (("BinningVerticalMode",), "enum"),
    "DecimationHorizontal": (("DecimationHorizontal",), "int"),
    "DecimationVertical": (("DecimationVertical",), "int"),
    "SensorReadoutMode": (("SensorReadoutMode",), "enum"),
    "SensorShutterMode": (("SensorShutterMode",), "enum"),
    "ExposureMode": (("ExposureMode",), "enum"),
    "DeviceTemperature": (("DeviceTemperature", "TemperatureAbs"), "float"),
    "DeviceTemperatureSelector": (("DeviceTemperatureSelector",), "enum"),
    "AcquisitionFrameRateEnable": (("AcquisitionFrameRateEnable",), "bool"),
    "AcquisitionFrameRate": (("AcquisitionFrameRate", "AcquisitionFrameRateAbs"), "float"),
    "DeviceLinkThroughputLimit": (("DeviceLinkThroughputLimit",), "int"),
    "DeviceLinkThroughputLimitMode": (("DeviceLinkThroughputLimitMode",), "enum"),
})


class BaslerCamera:
    def __init__(self, serial=None):
        self.serial = serial
        self.camera = None
        self.runtime = provenance()

    def open(self):
        # Initialize pylon before importing NumPy: the Linux native runtimes can
        # crash at interpreter shutdown when initialized in the opposite order.
        from pypylon import genicam, pylon

        self.pylon, self.genicam = pylon, genicam
        factory = pylon.TlFactory.GetInstance()
        devices = list(factory.EnumerateDevices())
        if self.serial:
            devices = [d for d in devices if d.GetSerialNumber() == self.serial]
        if not devices:
            raise RuntimeError("No Basler camera found. Check power, USB/GigE, pylon drivers and permissions.")
        if len(devices) != 1:
            raise RuntimeError("Multiple cameras found; select one with --serial.")
        self.camera = pylon.InstantCamera(factory.CreateDevice(devices[0]))
        # Each preview/capture explicitly requests a new frame. No stale free-run queue.
        self.camera.RegisterConfiguration(pylon.SoftwareTriggerConfiguration(),
                                         pylon.RegistrationMode_ReplaceAll, pylon.Cleanup_Delete)
        try:
            self.camera.Open()
            self.converter = pylon.ImageFormatConverter()
            self.converter.OutputPixelFormat = pylon.PixelType_RGB8packed
            self.converter.OutputBitAlignment = pylon.OutputBitAlignment_MsbAligned
            info = self.camera.GetDeviceInfo()
            self.identity = {"model": info.GetModelName(), "serial": info.GetSerialNumber(),
                             "transport": info.GetDeviceClass(),
                             "simulated": info.GetDeviceClass() == "BaslerCamEmu"}
            self.camera.StartGrabbing(pylon.GrabStrategy_OneByOne)
        except Exception:
            self.close()
            raise

    def close(self):
        # Release SDK-owned converter resources before the pylon runtime shuts down.
        self.converter = None
        if self.camera is not None:
            if self.camera.IsGrabbing():
                self.camera.StopGrabbing()
            self.camera.Close()
            self.camera = None

    def _node(self, key):
        if key not in FEATURES:
            raise ValueError(f"Unsupported setting: {key}")
        aliases, kind = FEATURES[key]
        for name in aliases:
            try:
                node = self.camera.GetNodeMap().GetNode(name)
            except self.genicam.LogicalErrorException:
                continue
            if node is not None and self.genicam.IsReadable(node):
                if kind == "number":
                    raw = node.GetNode() if hasattr(node, "GetNode") else node
                    kind = "int" if raw.GetPrincipalInterfaceType() == self.genicam.intfIInteger else "float"
                return name, node, kind
        raise ValueError(f"Setting unavailable on this camera: {key}")

    def _settings(self, include_unavailable=False):
        result = {}
        for key in FEATURES:
            try:
                name, node, kind = self._node(key)
                item = {"node": name, "kind": kind, "value": node.GetValue(),
                        "writable": bool(self.genicam.IsWritable(node)), "availability": "readable"}
                if hasattr(node, "GetUnit"):
                    item["unit"] = node.GetUnit()
                if kind == "enum":
                    item["choices"] = [entry.GetSymbolic() for entry in node.GetEntries()
                                       if self.genicam.IsAvailable(entry)]
                elif kind in ("int", "float"):
                    item.update(min=node.GetMin(), max=node.GetMax())
                    if kind == "int":
                        item["step"] = node.GetInc()
                result[key] = item
            except Exception as exc:
                if include_unavailable:
                    result[key] = {"availability": "unavailable_or_unreadable", "error": str(exc)}
        return result

    def _inventory(self, nodemap):
        values = {}
        scalar_types = {self.genicam.intfIInteger, self.genicam.intfIFloat, self.genicam.intfIBoolean,
                        self.genicam.intfIEnumeration, self.genicam.intfIString}
        for node in nodemap.GetNodes():
            raw = node.GetNode() if hasattr(node, "GetNode") else node
            name = raw.GetName()
            try:
                if not raw.IsFeature() or raw.GetPrincipalInterfaceType() not in scalar_types:
                    continue
                if not self.genicam.IsReadable(node):
                    values[name] = {"availability": "unreadable"}
                    continue
                value = node.GetValue()
                if isinstance(value, float) and not math.isfinite(value):
                    value = str(value)
                values[name] = {"availability": "readable", "value": value,
                                "selected_by": [n.GetName() for n in raw.GetSelectingFeatures()]}
            except Exception as exc:
                values[name] = {"availability": "read_error", "error": str(exc)}
        return values

    def snapshot(self):
        self.camera.StopGrabbing()
        try:
            settings = self._settings(include_unavailable=True)
            banks = {}
            # Read common selector banks and restore each selector, never write a
            # selected value. Other selector-indexed registers remain explicitly partial.
            for selector, names in {"GainSelector": ["Gain"], "BlackLevelSelector": ["BlackLevel"],
                                    "BalanceRatioSelector": ["BalanceRatio"],
                                    "ColorTransformationValueSelector": ["ColorTransformationValue"]}.items():
                try:
                    _, node, _ = self._node(selector)
                except ValueError:
                    banks[selector] = {"availability": "unavailable_or_unreadable"}
                    continue
                original = node.GetValue()
                choices = settings[selector].get("choices", [original])
                if not self.genicam.IsWritable(node):
                    choices = [original]
                bank = {"original": original, "all_choices_visited": len(choices) == len(settings[selector].get("choices", [])), "values": {}}
                try:
                    for choice in choices:
                        if choice != node.GetValue():
                            node.SetValue(choice)
                        selected = self._settings(include_unavailable=True)
                        bank["values"][choice] = {name: selected[name] for name in names}
                finally:
                    if node.GetValue() != original:
                        node.SetValue(original)
                banks[selector] = bank
            inventory = self._inventory(self.camera.GetNodeMap())
            try:
                persistence = {"text": self.pylon.FeaturePersistence.SaveToString(self.camera.GetNodeMap())}
            except Exception as exc:
                persistence = {"error": str(exc)}
            stable = {key: spec.get("value") for key, spec in settings.items() if key not in ("DeviceTemperature", "DeviceTemperatureSelector")}
            return {"captured_utc_ns": time.time_ns(), "camera": self.identity, "controls": settings,
                    "selector_banks": banks, "active_scalar_inventory": inventory, "feature_persistence": persistence,
                    "configuration_sha256": digest_json({"camera": self.identity, "controls": stable, "selector_banks": banks}),
                    "audit": processing_audit(settings), "runtime": self.runtime,
                    "coverage": "Readable GenICam scalar features, common selector banks, and SDK streamable persistence. Hidden sensor operations, arbitrary LUT contents and all selector combinations are NOT verified."}
        finally:
            self.camera.StartGrabbing(self.pylon.GrabStrategy_OneByOne)

    def enable_chunks(self):
        self.camera.StopGrabbing()
        report = {"enabled": [], "unavailable": [], "errors": {}}
        try:
            mode = self.camera.GetNodeMap().GetNode("ChunkModeActive")
            if mode is None or not self.genicam.IsWritable(mode):
                return {"supported": False, "note": "Chunk mode unavailable; no per-frame settings claim."}
            mode.SetValue(True)
            selector = self.camera.GetNodeMap().GetNode("ChunkSelector")
            original = selector.GetValue()
            choices = [entry.GetSymbolic() for entry in selector.GetEntries() if self.genicam.IsAvailable(entry)]
            try:
                for name in ("Timestamp", "ExposureTime", "Gain", "FrameID", "Framecounter", "CRCChecksum", "PayloadCRC16", "LineStatusAll"):
                    if name not in choices:
                        report["unavailable"].append(name)
                        continue
                    try:
                        selector.SetValue(name)
                        self.camera.GetNodeMap().GetNode("ChunkEnable").SetValue(True)
                        report["enabled"].append(name)
                    except Exception as exc:
                        report["errors"][name] = str(exc)
            finally:
                selector.SetValue(original)
            return {"supported": True, **report}
        except self.genicam.LogicalErrorException:
            return {"supported": False, "note": "Chunk mode unavailable; no per-frame settings claim."}
        finally:
            self.camera.StartGrabbing(self.pylon.GrabStrategy_OneByOne)

    def settings(self):
        # ROI / pixel format are often locked while grabbing. Report their idle capability.
        self.camera.StopGrabbing()
        try:
            return self._settings()
        finally:
            self.camera.StartGrabbing(self.pylon.GrabStrategy_OneByOne)

    def set_setting(self, key, value):
        self.camera.StopGrabbing()
        try:
            _, node, kind = self._node(key)
            if not self.genicam.IsWritable(node):
                raise ValueError(f"{key} is read-only in the current mode; check automatic controls.")
            if kind == "bool" and not isinstance(value, bool):
                raise ValueError("Expected a boolean")
            if kind in ("int", "float"):
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                    raise ValueError("Expected a finite number")
                if kind == "int" and int(value) != value:
                    raise ValueError("Expected an integer")
                value = int(value) if kind == "int" else float(value)
            node.SetValue(value)
            return self._settings()
        finally:
            self.camera.StartGrabbing(self.pylon.GrabStrategy_OneByOne)

    def grab(self, record=False):
        state = self.snapshot() if record else None
        pylon = self.pylon
        if not self.camera.WaitForFrameTriggerReady(10000, pylon.TimeoutHandling_ThrowException):
            raise RuntimeError("Camera is not ready for a software trigger")
        _, exposure_node, _ = self._node("ExposureTime")
        timeout_ms = max(30000, math.ceil(float(exposure_node.GetValue()) / 1000) + 30000)
        triggered_ns = time.time_ns()
        self.camera.ExecuteSoftwareTrigger()
        result = self.camera.RetrieveResult(timeout_ms, pylon.TimeoutHandling_ThrowException)
        try:
            if not result.GrabSucceeded():
                raise RuntimeError(result.GetErrorDescription())
            received_ns = time.time_ns()
            has_crc = bool(result.HasCRC())
            crc_ok = bool(result.CheckCRC()) if has_crc else None
            if crc_ok is False:
                raise RuntimeError("Camera payload CRC check failed")
            # Preserve the SDK-delivered payload BEFORE array unpacking/conversion.
            # This is not a USB packet trace; transport headers are not included.
            payload_size = int(result.GetPayloadSize())
            payload = bytes(memoryview(result.GetBuffer())[:payload_size]) if record else None
            if record and len(payload) != payload_size:
                raise RuntimeError("SDK payload length differs from reported payload size")
            array = result.GetArray().copy()
            jpeg, preview_error = None, None
            try:
                converted = self.converter.Convert(result)
                jpeg = jpeg_bytes(converted.GetArray())
            except Exception as exc:
                # A display conversion failure must not discard a valid measurement.
                preview_error = str(exc)
            settings = {key: item["value"] for key, item in self._settings().items()}
            chunks = self._inventory(result.GetChunkDataNodeMap()) if result.IsChunkDataAvailable() else {}
            return Frame(array, jpeg, {
                "camera": self.identity, "settings_readback": settings,
                "pixel_format": str(self.camera.PixelFormat.GetValue()),
                "camera_timestamp_ticks": int(result.GetTimeStamp()),
                "block_id": int(result.GetBlockID()),
                "host_trigger_utc_ns": triggered_ns, "host_received_utc_ns": received_ns,
                "payload": {"bytes": payload_size, "pixel_type_pfnc": int(result.GetPixelType()),
                            "payload_type": int(result.GetPayloadType()), "image_size_bytes": int(result.GetImageSize()),
                            "padding_x_bytes": int(result.GetPaddingX()), "padding_y_bytes": int(result.GetPaddingY()),
                            "offset_x": int(result.GetOffsetX()), "offset_y": int(result.GetOffsetY()),
                            "crc_present": has_crc, "crc_passed": crc_ok,
                            "boundary": "SDK-delivered payload; includes chunks when supplied, not USB/GigE wire headers"},
                "chunks": {"available": bool(result.IsChunkDataAvailable()), "values": chunks},
                "array_encoding": {"dtype_descriptor": array.dtype.str, "unpacked_by": "pypylon GrabResult.GetArray"},
                "preview": {"error": preview_error, "pipeline": ["pylon RGB8 conversion (may demosaic / reduce depth)", "Pillow thumbnail <=1280x960", "JPEG quality 80"], "measurement_data": False},
                "timestamp_note": "Camera ticks are not UTC. Settings are read after acquisition, not per-frame chunks.",
            }, payload=payload, state=state)
        finally:
            result.Release()


class SimulatedCamera:
    """Explicit test/demo source, never an automatic fallback from failed hardware."""
    def __init__(self, serial=None):
        self.identity = {"model": "Simulated test pattern", "serial": "SIMULATED", "simulated": True}
        self.count = 0
        self.values = {"ExposureTime": 10000.0, "Gain": 0.0, "Width": 640, "Height": 480,
                       "ExposureAuto": "Off", "GainAuto": "Off", "PixelFormat": "Mono12", "BlackLevel": 64.0}

    def open(self):
        pass

    def close(self):
        pass

    def settings(self):
        return {key: {"node": key, "kind": "enum" if isinstance(value, str) else "float", "value": value,
                      "writable": key in ("ExposureTime", "Gain"), "availability": "readable",
                      "choices": [value] if isinstance(value, str) else [], "min": 1 if key == "ExposureTime" else 0,
                      "max": 100000, "step": 1} for key, value in self.values.items()}

    def snapshot(self):
        settings = {key: self.settings().get(key, {"availability": "unavailable_or_unreadable"}) for key in FEATURES}
        return {"camera": self.identity, "controls": settings, "audit": processing_audit(settings),
                "configuration_sha256": digest_json({"camera": self.identity, "controls": self.values}), "runtime": provenance(),
                "coverage": "Simulation only; no physical sensor evidence."}

    def enable_chunks(self):
        return {"supported": False, "note": "Simulated source has no real camera chunks."}

    def set_setting(self, key, value):
        if key not in ("ExposureTime", "Gain") or isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("Unsupported simulated setting")
        if not math.isfinite(value) or not (1 if key == "ExposureTime" else 0) <= value <= 100000:
            raise ValueError("Setting out of bounds")
        self.values[key] = value
        return self.settings()

    def grab(self, record=False):
        import numpy as np

        self.count += 1
        y, x = np.indices((480, 640))
        # Stable synthetic irradiance pattern with exposure response and seeded
        # frame noise. This supports control-board tests, not physical calibration.
        rng = np.random.default_rng(self.count)
        signal = (x * 2 + y) * self.values["ExposureTime"] / 10000 * (1 + self.values["Gain"] / 10)
        raw = np.clip(np.rint(signal + 64 + rng.normal(0, 2, signal.shape)), 0, 4095).astype(np.uint16)
        return Frame(raw, jpeg_bytes((raw >> 4).astype(np.uint8)), {
            "camera": self.identity, "settings_readback": dict(self.values), "pixel_format": "Mono12",
            "block_id": self.count, "host_received_utc_ns": time.time_ns(),
            "payload": {"boundary": "Synthetic array bytes, not camera transport", "bytes": raw.nbytes},
            "chunks": {"available": False, "values": {}},
        }, payload=raw.tobytes() if record else None, state=self.snapshot() if record else None)
