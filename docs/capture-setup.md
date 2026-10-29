# Basler capture service

The first implementation covers live preview, camera configuration, fresh software-triggered captures, and verified Pi-to-host transfer. Robot movement is not implemented: the host must first confirm the robot has settled, then request a capture and wait for its acknowledgement.

## Stack

- Ubuntu ARM64 or Raspberry Pi OS 64-bit / Python 3.10+, Basler `pypylon` for USB or GigE cameras.
- FastAPI / Uvicorn, one process and one camera owner. A lock serializes preview, settings and capture requests.
- HTML/CSS/JavaScript panel; MJPEG preview at 3 fps by default, reduced to at most 1280 Ã— 960. Preview is deliberately separate from dataset storage.
- Full pixel arrays in NumPy `.npy` files (no JPEG loss or bit-depth reduction), JSON metadata and SHA-256 hashes. The SDK may unpack packed pixel formats. This is an initial storage format; final dataset interchange format remains to be agreed.
- SSH port forwarding for the panel/API and rsync over SSH for resumable transfer. The API binds only to loopback and has no separate login.

## Optional desktop hotspot and new-PC launcher

For a new desktop, follow the [Quickstart](../QUICKSTART.md):
`python scripts/run.py --pi PI_IP` installs desktop dependencies, sets up SSH
using terminal prompts, connects and opens the browser. The Pi service must
already be installed. To prepare or repair the environment separately, run
`python scripts/setup_env.py`. Both commands create `.venv` and bootstrap missing
pip with Python ensurepip; global pip is not required. If Python omits ensurepip,
install python3-venv/python3-pip on Ubuntu/Debian or repair the full Python
installation on Windows, then retry. Host transfers use rsync if present, otherwise OpenSSH scp;
both paths verify the same archived checksums before publishing a capture.

After installing the package, the main commands also accept `--hotspot`:

```sh
dataset-dashboard --hotspot --pi PI_IP --connect --open-browser
# Capture service on a host that should itself create the network:
dataset-capture --hotspot
# Standalone hotspot script:
dataset-hotspot
```

The network is **DatasetCapture**, password **datasetcapture**. The scripts
request 2.4 GHz and WPA2 for compatibility. Windows uses Windows PowerShell 5.1
and the Mobile hotspot API; the wireless driver, upstream connection, policy
and PowerShell script policy must permit it. Linux uses NetworkManager,
a dedicated profile with autoconnect disabled, and host address `10.42.0.1/24`.
Use `--hotspot-interface wlan0` with the app/launcher (or `--interface wlan0`
with `dataset-hotspot`) when there are multiple Linux Wi-Fi adapters.
Linux may require approval from NetworkManager/Polkit; a single Wi-Fi adapter
will disconnect from its current network when switched to access-point mode.
Windows assigns its own hotspot subnet, commonly `192.168.137.0/24`.

Without the flag no hotspot operations run. Failure to start the hotspot stops
startup with an error. The hotspot remains enabled after the app exits; disable
it in Windows Settings or, on Linux, with
`nmcli connection down dataset-capture-hotspot`.
An already active different Windows hotspot is not replaced.
No live hotspot change was validated on the development laptop; it previously
failed client authentication even through Settings. A phone hotspot is still an
option: omit `--hotspot` and supply the Pi's actual private LAN IP.

## Network and first connection

The desktop hosts **DatasetCapture** and shares its Ethernet internet connection. Join this network from the Pi using the password supplied in chat. Credentials are not stored in this repository.

On Ubuntu Desktop or Raspberry Pi OS with NetworkManager, use the Wi-Fi settings or `sudo nmtui` to join the network. After any running apt upgrade finishes, install and enable SSH:

```bash
sudo apt install openssh-server
sudo systemctl enable --now ssh
hostname -I
```

The desktop hotspot address is currently `10.42.0.1`; the Pi receives another address in `10.42.0.0/24`. Verify the Pi can resolve and reach the internet before installing packages:

```bash
getent hosts pypi.org
curl -I --max-time 15 https://pypi.org
```

Use the actual Pi address in place of `PI_IP` below. From the desktop repository directory:

```bash
ssh cameramodule@PI_IP 'mkdir -p /home/cameramodule/dataset_capture'
rsync -rt pyproject.toml dataset_capture scripts deploy cameramodule@PI_IP:/home/cameramodule/dataset_capture/
ssh -t cameramodule@PI_IP 'cd /home/cameramodule/dataset_capture && bash scripts/setup_pi.sh'
```

The setup installs dependencies and enumerates cameras. It does not configure robot motion. Basler recommends installing the matching pylon Software Suite as well, particularly for device permissions and transport setup. A USB camera may need the vendor's udev rules; GigE requires a reachable camera subnet and appropriate power/PoE. Inspect the exact camera model before changing network or camera transport settings. Close pylon Viewer before opening the camera here.

## Run on the Pi and open from the desktop

The deployed Pi (`10.42.0.141`, user `cameramodule`) now runs the enabled
`dataset-capture` systemd service automatically at boot. On the desktop:

```bash
cd /home/magnus/projects/dataset_capture
.venv/bin/dataset-dashboard --port 8001
```

Open <http://127.0.0.1:8001> and select **Connect**. The dashboard manages
its SSH tunnel. A working terminal SSH session alone does not imply that
the Pi capture service is installed or running.

In **Save capture**, enter an absolute desktop folder path. It defaults to
`captures` under the dashboard's working directory and is remembered in this
browser. Each press captures on the Pi, transfers that capture into its own
subfolder, and verifies all recorded file checksums before showing **Saved and
verified**. A new capture ID is prepared after success. **Retry transfer**
copies the already saved image without acquiring another frame. Existing
different archives are never overwritten, and Pi originals are retained.
This automatic transfer applies to individual Save capture actions; calibration
series still use the host synchronization command below.

For this camera's USB permissions, the deployment uses a dedicated group:

```bash
sudo groupadd -f dataset-camera
sudo usermod -a -G dataset-camera cameramodule
sudo install -m 644 deploy/70-dataset-basler.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=usb --attr-match=idVendor=2676
sudo udevadm settle
sudo systemctl restart dataset-capture
```

These steps are already applied on the current Pi. The rule matches USB
vendor/product `2676:ba05`. Restarting the service picks up group membership;
desktop login is not required.

The following manual launch/tunnel instructions are alternatives for development.
Stop the systemd service before manually starting another camera owner.

On the Pi:

```bash
cd ~/dataset_capture
.venv/bin/dataset-probe
.venv/bin/dataset-capture --output ~/captures
```

With multiple cameras, add `--serial CAMERA_SERIAL`. If startup cannot open the camera, the panel still runs and reports the error. Reconnect after correcting it. Simulation is only enabled by the explicit `--simulate` flag.

On the desktop, leave this tunnel running:

```bash
ssh -N -o ExitOnForwardFailure=yes -L 8000:127.0.0.1:8000 cameramodule@PI_IP
```

Open <http://127.0.0.1:8000>. If local port 8000 is occupied, forward `8001:127.0.0.1:8000` and open port 8001. Use the same port with `dataset-host --url` (see capture example below).

The panel shows controls supported by the connected camera, including exposure, gain, pixel format, ROI, white-balance auto and gamma where available. Apply one setting at a time; ranges/read-only states are read from the device. Settings files can be exported/imported. Import is sequential, stops on the first failure and reports that earlier changes may already have applied. Triggering is fixed to software FrameStart in this initial version; external triggering requires a separate acquisition path.

Optional service installation after a successful bench test, on the Pi:

```bash
sudo install -m 644 deploy/dataset-capture.service /etc/systemd/system/dataset-capture.service
sudo systemctl daemon-reload
sudo systemctl enable --now dataset-capture
journalctl -u dataset-capture -f
```

Adjust the unit's username and paths if using a different account. Do not launch a second process against the same camera or output folder.

## Capture coordination and transfer

Create a JSON context file containing explicit units and coordinate frames for robot poses, plus lighting/session identifiers. For example:

```json
{"session":"pilot-01","robot_pose":{"frame":"base","position_m":[0.1,0.2,0.3],"rotation_vector_rad":[0,0,0]},"lighting":{"preset":"fixed-01"}}
```

After the robot has settled, on the desktop:

```bash
.venv/bin/dataset-host capture pilot-01-pose-001 --context pose.json --url http://127.0.0.1:8000
.venv/bin/dataset-host sync cameramodule@PI_IP --source /home/cameramodule/captures --destination captures
```

`POST /api/captures` receives `{"capture_id":"pilot-01-pose-001","context":{...}}`. It triggers a new frame, writes and fsyncs files, then atomically publishes a completed directory before acknowledging. Retries with the same ID/context return the saved result even after service restart; reusing an ID with different context returns HTTP 409. A timeout is an uncertain outcome: retry the same ID before advancing the robot. The protocol does not guarantee an exposure happens only once if power fails before the saved directory is published.

Transfer excludes incomplete `.partial-*` directories, resumes interrupted downloads and verifies image/preview size and hashes against metadata after rsync succeeds. Pi originals are retained. Consumers should use data only after verification succeeds. SSH host-key checking is enabled by default. This first version synchronizes on command; a continuous transfer scheduler is not yet included.

Metadata records camera identity, pixel format, array shape/dtype, settings readback, camera timestamp ticks, host trigger/receipt times, and the supplied pose/light context. Camera ticks are not synchronized UTC. Readback settings are queried after acquisition; automatic settings are not guaranteed to describe the exact exposure unless the corresponding per-frame chunks are available and enabled. For controlled datasets, disable auto exposure/gain/white balance and record fixed settings. Preview and capture use software triggers, which do not provide hard real-time timing. Motion-synchronized exposure and clock alignment need hardware-specific work.

## Local development

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/pytest
.venv/bin/dataset-capture --simulate --output /tmp/dataset-capture-demo --port 8001
```

Simulation is prominently labelled and stored metadata includes `simulated: true`. Tests cover pixel depth, atomic publication, retry/concurrency behavior, invalid paths, corrupted transfers, camera errors and API validation.

With the optional Basler SDK installed, tests also exercise its camera emulator in a subprocess, including settings, 12-bit capture and native-library shutdown. The service initializes pylon before importing NumPy: on this Linux desktop, importing NumPy first caused a native shutdown crash with both pypylon 4.2 and 26.8. Use the provided CLI entry point to preserve initialization order.

References: [Basler pypylon](https://github.com/basler/pypylon), [Raspberry Pi remote access](https://www.raspberrypi.com/documentation/computers/remote-access.html).

## Radiometric experiments

Read the [complete measurement chain and protocol](../dataset_capture/protocol.md) before collecting calibration data. The board now offers DN inspection, processing snapshots, optical setup records, available frame chunks and repeated exposure sweeps. Schema-2 captures also archive the SDK payload and camera-state evidence. These features do not establish absolute radiance without a measured reference.

`constraints-tested.txt` records the local desktop dependency versions used during validation; it is not a verified ARM64 compatibility lock. Validate dependency availability and native SDK behavior on the Pi before adopting those pins.

## Desktop connection dashboard

Run `.venv/bin/dataset-dashboard` on the desktop (or `python -m dataset_capture.desktop`)
and open <http://127.0.0.1:8001>. Enter the Pi hotspot address and username, then
choose **Connect**. The Pi capture service must already be running on loopback
port 8000. The dashboard supervises an SSH tunnel using the desktop's approved
SSH key/agent and known-hosts entry. It retries the tunnel after interruption;
Disconnect closes the tunnel, not the Pi service or a running measurement series.
No password is stored in the web application.

The dashboard remains on the desktop during Wi-Fi loss. A separate heartbeat
checks the Pi service every two seconds with a two-second network timeout. A
reply older than six seconds cannot show connected. Camera readiness and image
freshness are separate indicators; a working SSH process alone is not a healthy
Pi service. Heartbeats never acquire the camera lock. Browser requests also have
timeouts; returning to a backgrounded tab immediately reevaluates heartbeat age.
Capture requests are not automatically replayed. An uncertain save keeps its ID
and context for an explicit retry after reconnecting. A running series continues
on the Pi; its status is recovered when the connection returns.

On 2026-10-19, Pi SSH access and Basler USB detection were verified, but
larger wireless packets suffered loss/retransmission. The devices were far apart.
A temporary hotspot MTU reduction improved a small test; it was restored to the
original automatic setting when connection work was stopped. Do not assume the
root cause or sustained image-transfer performance is established. Move the Pi
closer and measure again before deploying. Standard SSH negotiation and host-key
checking remain enabled. The desktop public key was installed with explicit user
approval. Pi dependency installation was started but completion is unverified;
check apt/dpkg state before resuming installation. No capture service is confirmed
running on the Pi yet.

The dashboard accepts private IPv4 addresses in 10.0.0.0/8, 172.16.0.0/12 and
192.168.0.0/16, including Windows and phone hotspots. Individual Save capture
actions transfer and verify data on the desktop; other Pi data still needs
`dataset-host sync`. Connection status does not imply a backup.
