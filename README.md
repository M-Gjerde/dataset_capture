# Anomaly detection dataset with material decomposition

**New PC? [Quickstart: clone, run, open the camera](QUICKSTART.md).**

A practical dataset of metal and glass objects for geometry and lighting estimation used to train anamoly detectors.

**First milestone:** capture one object with recorded camera poses and light settings, then check whether the data is usable in our renderer.

- [TODO](TODO.md): next actions, grouped by subsystem.
- [Shopping list](docs/shopping-list.md): hardware candidates and blackout prices.
- [Collaboration](docs/collaboration.md): edit and track work in GitHub's browser UI.
- [Capture software setup](docs/capture-setup.md): Pi hotspot connection, Basler preview/settings panel, capture API and verified host transfer.

## What we have

- UR robot (exact model to check) on a 120 Ã— 80 cm table.
- Existing cameras (manufacturer, models and interfaces to check).
- End-effector attachment (QC75 catalogue and a Rhino attachment model in this folder).
- Room at the Utzon center.

Preferred approach: camera and Raspberry Pi on the end-effector, saving images locally. Camera compatibility and power are not yet resolved.

Keep large captures outside Git, on backed-up shared storage. This repo holds plans, code, calibration files and manifests.

The [radiometric measurement protocol](dataset_capture/protocol.md) documents the sensor-to-host chain, processing evidence, calibration experiments and limits of absolute-scale claims.
