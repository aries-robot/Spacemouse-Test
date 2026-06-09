# SpaceMouse pyspacemouse test

This repository is a smoke test for checking 3Dconnexion SpaceMouse connectivity and input with `pyspacemouse` in a `uv` virtual environment.

## Installation

```bash
uv venv
uv pip install "pyspacemouse>=2.0.0,<3.0.0"
```

## Linux hidraw Permissions

On Linux, if `/dev/hidraw*` is owned as `root root 600` or `root root 660`, device detection may work but opening the device will fail. Immediately after installation, install the provided udev rule and reconnect the device.

```bash
sudo cp udev/99-3dconnexion-spacemouse.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo udevadm trigger
```

## Running

First, probe for the device index that can be opened, then run the test with the detected `N` value.

```bash
.venv/bin/python spacemouse_test.py --probe-indices
.venv/bin/python spacemouse_test.py --device-index N
```

If the device is working correctly, axis values and button states are printed when you move the SpaceMouse or press its buttons.

## Diagnostic Options

```bash
.venv/bin/python spacemouse_test.py --list-hid --scan-only
.venv/bin/python spacemouse_test.py --list-supported --scan-only
.venv/bin/python spacemouse_test.py --duration 0 --show-idle
.venv/bin/python spacemouse_test.py --probe-indices
```

If the device is visible on Linux but cannot be opened, check the `/dev/hidraw*` permissions or the udev rule for 3Dconnexion devices.
