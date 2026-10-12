# Anomaly detection dataset with material decomposition

A practical dataset of metal and glass objects for geometry and lighting estimation used to train anamoly detectors.

**First milestone:** capture one object with recorded camera poses and light settings, then check whether the data is usable in our renderer.

- [TODO](TODO.md): next actions, grouped by subsystem.
- [Research notes](docs/research-plan.md): options and open questions.
- [Shopping list](docs/shopping-list.md): hardware candidates and blackout prices.
- [Collaboration](docs/collaboration.md): edit and track work in GitHub's browser UI.

## What we have

- UR robot (exact model to check) on a 120 × 80 cm table.
- Existing cameras (manufacturer, models and interfaces to check).
- End-effector attachment (QC75 catalogue and a Rhino attachment model in this folder).
- Room at the Utzon center.

Preferred approach: camera and Raspberry Pi on the end-effector, saving images locally. Camera compatibility and power are not yet resolved.

Keep large captures outside Git, on backed-up shared storage. This repo holds plans, code, calibration files and manifests.

Research checked 12 October 2026. No purchases or supplier enquiries made. GitHub publishing is being handled by the user.
