# Quickstart

Requires **Git**, **Python 3.10+** (with pip/venv), and **OpenSSH Client** (`ssh`, `ssh-keygen`, `scp`). Sign in to GitHub when cloning this private repository.

1. Clone and enter the repository:
   ```sh
   git clone https://github.com/M-Gjerde/dataset_capture.git
   cd dataset_capture
   ```
2. Connect the PC and Pi to the same Wi-Fi. Run (`10.233.204.25` is the current Pi address; replace it if it changes):
   ```sh
   python scripts/run.py --pi 10.233.204.25
   ```
   On first use, verify the Pi fingerprint and enter the **Pi login password** when prompted. Dependencies and SSH key access are set up automatically.
3. The browser opens automatically at **http://127.0.0.1:8001**. If needed, open that address yourself.

**Optional PC hotspot:** run `python scripts/run.py --hotspot`, join **DatasetCapture** / **datasetcapture** from the Pi, then enter its new IP when prompted. Windows needs Mobile hotspot support and an upstream connection; Linux needs NetworkManager and may request network privileges. A single Linux Wi-Fi adapter switches away from its existing network.

The Pi must already have its camera service installed and running; see [Pi setup](docs/capture-setup.md). Stop the app with Ctrl+C. An explicitly started hotspot stays on until disabled in system settings.
