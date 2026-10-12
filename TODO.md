# TODO

Once completed we should have one working usable capture and we can scale up from there.


## Final Goal:
- [ ] Choose one simple pilot object and recover geometry + material parameters under known illumination.

### 1. Put everything together (Sorted by milestone difficulty)

- [ ] **1. Bench capture:** Use the selected camera and controller to save one image with recorded capture settings. Requires **2 + 6**.
- [ ] **2. Robot capture:** Mount the working camera setup and run a short movement script that saves an image at each capture location. Adds **3**.
- [ ] **3. Controlled illumination:** Repeat the robot capture with fixed, recorded lighting in the blackout room, check leakage and unwanted reflections. Adds **4 + 5**.
- [ ] **4. Calibrated capture:** Capture the pilot object with calibrated camera intrinsics/extrinsics, characterized illumination and the agreed image format/metadata. Brings **2–6** together.
- [ ] **5. Reconstruction:** Use that capture to recover geometry and material parameters under known illumination, compare rendered and captured images before expanding the dataset.

### 2. Camera and Raspberry Pi Hardware

- [ ] Find out which camera we will use and its specs.
- [ ] Find out which controller for the camera we might use (Raspberry Pi or something else)
- [ ] Find out which camera lenses and focus distances we have to consider.
- [ ] Check the selected camera's Pi SDK support and if it supports what is defined in **6. Camera Calibration and Data**
- [ ] Measure power/storage needs and how setup might fit into **3. Robot and attachment**

### 3. Robot and attachment

- [ ] Design and print an attachment for the camera/Pi bracket.
- [ ] Check mounting, payload, cables and a small capture path with the robot operator.
- [ ] Write a reusable robot movement script to move the robot to the capture locations timed with the camera controller to capture images at each pose.

### 4. Lighting

- [ ] Inventory available lights and controllers, find out if we need to buy calibrated lights or reuse the ones we have.
- [ ] Select and rigidly mount pilot lights, record their positions and settings.
- [ ] Decide whether relative light calibration is enough or absolute radiometric calibration is required.

### 5. Blackout Room

- [ ] Inspect the Utzon room we will be using for the capture.
- [ ] Measure the room and the robot's planned motion envelope, including lights and access.
- [ ] Compare window blackout with the priced tent options. 
- [ ] Test daylight leakage and unwanted reflections using the actual camera/exposures.

### 6. Camera Calibration and data

- [ ] Camera calibration: Extrinsic parameters and intrinsic parameters.
- [ ] Settle on final capture format: RAW, white balancing, exposure, gain, gamma etc..
- [ ] Define image IDs and metadata: camera pose, exposure.



## Decisions and log:

### Camera Hardware








