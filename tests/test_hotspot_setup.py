import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from dataset_capture import hotspot
from dataset_capture.desktop import ConnectionTarget, LocalSave, PiConnection, save_local_capture


def test_hotspot_is_opt_in():
    parser = argparse.ArgumentParser()
    hotspot.add_hotspot_arguments(parser)
    with patch.object(hotspot, "start_hotspot") as start:
        hotspot.configure_hotspot(parser.parse_args([]), parser)
        start.assert_not_called()


def test_hotspot_failure_stops_startup():
    parser = argparse.ArgumentParser()
    hotspot.add_hotspot_arguments(parser)
    with patch.object(hotspot, "start_hotspot", side_effect=hotspot.HotspotError("adapter refused")):
        with pytest.raises(SystemExit) as exc:
            hotspot.configure_hotspot(parser.parse_args(["--hotspot"]), parser)
    assert exc.value.code == 2


def test_windows_script_is_packaged_and_failure_reported():
    with patch.object(hotspot.platform, "system", return_value="Windows"), \
         patch.object(hotspot.shutil, "which", return_value="powershell.exe"), \
         patch.object(hotspot.subprocess, "run", return_value=SimpleNamespace(
             returncode=1, stdout="", stderr="Access denied")) as run:
        with pytest.raises(hotspot.HotspotError, match="Access denied"):
            hotspot.start_hotspot()
    command = run.call_args.args[0]
    assert Path(command[-1]).is_file()
    assert command[-2] == "-File"


def test_linux_profile_is_reused_without_duplicates():
    replies = ["wlan0:wifi", hotspot.PROFILE_UUID, "", ""]
    with patch.object(hotspot.platform, "system", return_value="Linux"), \
         patch.object(hotspot.shutil, "which", return_value="/usr/bin/nmcli"), \
         patch.object(hotspot, "_run", side_effect=replies) as run:
        hotspot.start_hotspot()
    commands = [call.args[0] for call in run.call_args_list]
    assert not any("add" in cmd for cmd in commands)
    assert any("modify" in cmd for cmd in commands)
    assert any("rsn" in cmd and "bg" in cmd for cmd in commands)


def test_multiple_wifi_adapters_require_selection():
    with patch.object(hotspot.platform, "system", return_value="Linux"), \
         patch.object(hotspot.shutil, "which", return_value="nmcli"), \
         patch.object(hotspot, "_run", return_value="wlan0:wifi\nwlan1:wifi") as run:
        with pytest.raises(hotspot.HotspotError, match="Select a Wi-Fi adapter"):
            hotspot.start_hotspot()
    assert run.call_count == 1


@pytest.mark.parametrize("address", ["10.233.204.25", "192.168.137.25", "172.16.2.10", "10.42.0.141"])
def test_private_pi_networks(address):
    assert ConnectionTarget(address=address).address == address


@pytest.mark.parametrize("address", ["127.0.0.1", "8.8.8.8", "::1", "example.com"])
def test_other_targets_rejected(address):
    with pytest.raises(ValueError):
        ConnectionTarget(address=address)


def test_explicit_identity_used_for_tunnel():
    connection = PiConnection(ConnectionTarget(address="10.233.204.25"), identity="key with spaces")
    with patch("dataset_capture.desktop.subprocess.Popen") as popen, \
         patch("dataset_capture.desktop.threading.Thread"):
        connection._launch()
    command = popen.call_args.args[0]
    assert command[1:3] == ["-i", "key with spaces"]
    assert "StrictHostKeyChecking=yes" in command


@pytest.mark.parametrize("corrupt", [False, True])
def test_scp_fallback_verifies_before_publish(tmp_path, corrupt):
    connection = Mock()
    connection.identity = "key with spaces"
    connection.snapshot.return_value = {"state": "online",
        "target": {"address": "10.233.204.25", "username": "cameramodule"}}
    connection.forward.return_value = (200, b'{"output":"/home/cameramodule/captures"}', "application/json")
    request = LocalSave(capture_id="test-1", destination=str(tmp_path))
    def transfer(command, **kwargs):
        assert command[0] == "scp"
        assert command[command.index("-i") + 1] == "key with spaces"
        archive = Path(command[-1])
        files = {}
        for name in ("image.npy", "preview.jpg"):
            body = b"example"
            (archive / name).write_bytes(body)
            files[name] = {"bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}
        (archive / "metadata.json").write_text(json.dumps(
            {"capture_id": "test-1", "schema_version": 1, "files": files}))
        if corrupt:
            (archive / "image.npy").write_bytes(b"bad")
    with patch("dataset_capture.desktop.shutil.which", return_value=None), \
         patch("dataset_capture.desktop.subprocess.run", side_effect=transfer):
        if corrupt:
            with pytest.raises(ValueError, match="Checksum mismatch"):
                save_local_capture(connection, request)
            assert not (tmp_path / "test-1").exists()
        else:
            assert save_local_capture(connection, request)["verified"]
            assert (tmp_path / "test-1" / "image.npy").is_file()
    assert not list(tmp_path.glob(".partial-*"))


def test_dashboard_flag_reaches_hotspot_and_autoconnect():
    from dataset_capture import desktop
    with patch("sys.argv", ["dataset-dashboard", "--hotspot", "--pi", "10.233.204.25", "--connect"]), \
         patch.object(hotspot, "start_hotspot") as start, \
         patch.object(desktop, "PiConnection") as connection, \
         patch("uvicorn.run") as server:
        desktop.main()
    start.assert_called_once()
    connection.return_value.connect.assert_called_once()
    server.assert_called_once()


def test_capture_flag_reaches_hotspot():
    from dataset_capture import app
    with patch("sys.argv", ["dataset-capture", "--simulate", "--hotspot"]), \
         patch.object(hotspot, "start_hotspot") as start, \
         patch("uvicorn.run") as server:
        app.main()
    start.assert_called_once()
    server.assert_called_once()


def test_launcher_help_needs_no_app_dependencies():
    import subprocess
    import sys
    result = subprocess.run([sys.executable, str(Path(__file__).parents[1] / "scripts" / "run.py"), "--help"],
                            capture_output=True, text=True)
    assert result.returncode == 0
    assert "--hotspot" in result.stdout


def test_launcher_reuses_dedicated_ssh_key(tmp_path):
    path = Path(__file__).parents[1] / "scripts" / "run.py"
    spec = importlib.util.spec_from_file_location("desktop_launcher", path)
    launcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launcher)
    key = tmp_path / ".ssh" / "id_dataset_capture"
    key.parent.mkdir()
    key.write_text("not-a-real-key")
    with patch.object(launcher.Path, "home", return_value=tmp_path), \
         patch.object(launcher.shutil, "which", return_value="ssh"), \
         patch.object(launcher.subprocess, "run", return_value=SimpleNamespace(returncode=0)) as run:
        assert launcher.setup_ssh("10.233.204.25", "cameramodule") == key
    assert run.call_count == 1
    assert run.call_args.args[0][1:3] == ["-i", str(key)]


def load_launcher():
    path = Path(__file__).parents[1] / "scripts" / "run.py"
    spec = importlib.util.spec_from_file_location("setup_launcher", path)
    launcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launcher)
    return launcher


@pytest.mark.parametrize("existing", [False, True])
def test_environment_bootstraps_missing_pip_even_with_stamp(tmp_path, existing):
    launcher = load_launcher()
    target = tmp_path / ".venv"
    python = target / ("Scripts/python.exe" if launcher.os.name == "nt" else "bin/python")
    if existing:
        python.parent.mkdir(parents=True)
        python.touch()
    (tmp_path / "pyproject.toml").write_text("project")
    target.mkdir(exist_ok=True)
    stamp = target / ".desktop-requirements"
    stamp.write_text(hashlib.sha256(b"project").hexdigest())
    replies = [SimpleNamespace(returncode=1), SimpleNamespace(returncode=0),
               SimpleNamespace(returncode=0), SimpleNamespace(returncode=0)]
    with patch.object(launcher, "ROOT", tmp_path), \
         patch.object(launcher.subprocess, "run", side_effect=replies) as process, \
         patch.object(launcher, "run") as run:
        assert launcher.environment() == python
    commands = [call.args[0] for call in process.call_args_list]
    assert any("ensurepip" in command for command in commands)
    assert any("install" in call.args[0] for call in run.call_args_list)
    if not existing:
        assert "--without-pip" in run.call_args_list[0].args[0]


def test_environment_reports_missing_ensurepip_without_success_stamp(tmp_path):
    launcher = load_launcher()
    target = tmp_path / ".venv"
    python = target / ("Scripts/python.exe" if launcher.os.name == "nt" else "bin/python")
    python.parent.mkdir(parents=True)
    python.touch()
    replies = [SimpleNamespace(returncode=1),
               SimpleNamespace(returncode=1, stderr="No module named ensurepip", stdout="")]
    with patch.object(launcher, "ROOT", tmp_path), \
         patch.object(launcher.subprocess, "run", side_effect=replies), \
         patch.object(launcher, "run") as run:
        with pytest.raises(RuntimeError, match="python3-venv"):
            launcher.environment()
    run.assert_not_called()
    assert not (target / ".desktop-requirements").exists()


def test_environment_reuses_healthy_install(tmp_path):
    launcher = load_launcher()
    target = tmp_path / ".venv"
    python = target / ("Scripts/python.exe" if launcher.os.name == "nt" else "bin/python")
    python.parent.mkdir(parents=True)
    python.touch()
    (tmp_path / "pyproject.toml").write_text("project")
    (target / ".desktop-requirements").write_text(hashlib.sha256(b"project").hexdigest())
    with patch.object(launcher, "ROOT", tmp_path), \
         patch.object(launcher.subprocess, "run", return_value=SimpleNamespace(returncode=0)), \
         patch.object(launcher, "run") as run:
        assert launcher.environment() == python
    run.assert_not_called()
