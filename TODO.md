# TODO

Start with one usable capture. Assign an owner when starting a task; record the result or blocker in its GitHub issue.

## 1. Put everything together

- [ ] Choose one pilot object and agree what the first capture must demonstrate.
- [ ] Prove that an existing camera can save images locally on a Pi. See **Camera**.
- [ ] Capture the object from a few robot poses under separately recorded lights. Requires **Robot**, **Camera**, **Lighting**, **Blackout** and **Calibration** below.
- [ ] Load that capture into the renderer; inspect pose, exposure and lighting errors before collecting more data.
- [ ] Decide the next objects, views and lights from the pilot results.

## 2. Camera and Raspberry Pi

- [ ] Photograph camera labels/connectors; list models, interfaces and existing lenses.
- [ ] Check the selected camera's Pi SDK support; test exposure control, triggering and local image saving on a bench.
- [ ] Test lens framing and focus on the pilot object before buying a lens.
- [ ] Measure power/storage needs; choose battery or regulated tool power before designing the Pi mount.

## 3. Robot and attachment

- [ ] Confirm robot model, controller and installed QC75 parts.
- [ ] Check the supplied CAD against the physical attachment and chosen camera/Pi.
- [ ] Design and print a fit-test piece, then the camera/Pi bracket.
- [ ] Check mounting, payload, cables and a small capture path with the robot operator.

## 4. Lighting

- [ ] Inventory available lights and controllers; test one light with the camera.
- [ ] Decide whether relative light calibration is enough or absolute radiometric calibration is required.
- [ ] Request area-light quotes specifying calibration data, control interface, emitting dimensions and delivery time. See shopping list.
- [ ] Select and rigidly mount pilot lights; record their positions and settings.

## 5. Blackout

- [ ] Measure the room and the robot's planned motion envelope, including lights and access.
- [ ] Compare window blackout with the priced tent options; confirm usable internal dimensions before ordering.
- [ ] Test daylight leakage and unwanted reflections using the actual camera/exposures.

## 6. Calibration and data

- [ ] Select a rigid calibration target; test camera intrinsics and robot-to-camera calibration with independent validation images.
- [ ] Agree how light geometry/output will be measured; test the method on a reference object.
- [ ] Define image IDs and metadata: camera pose, exposure, light state and calibration version.
- [ ] Choose shared storage and verify a backup of the pilot capture.
