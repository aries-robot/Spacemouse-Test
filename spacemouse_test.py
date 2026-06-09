#!/usr/bin/env python3
"""Smoke test a 3Dconnexion SpaceMouse through pyspacemouse."""

# Load standard library modules.
import argparse
import sys
import time

# Load HID SpaceMouse API.
import pyspacemouse

# Keep printed axis order stable.
AXES = ("x", "y", "z", "roll", "pitch", "yaw")


def main() -> int:
    """Run SpaceMouse discovery and read loop."""
    # Parse runtime options.
    parser = argparse.ArgumentParser(description="Test a SpaceMouse with pyspacemouse.")
    parser.add_argument("--device", help="Open a specific pyspacemouse device name.")
    parser.add_argument("--device-index", type=int, help="Open only this matching device index.")
    parser.add_argument("--duration", type=float, default=30.0, help="Read duration in seconds. Use 0 for forever.")
    parser.add_argument("--poll-hz", type=float, default=100.0, help="HID polling rate.")
    parser.add_argument("--print-hz", type=float, default=20.0, help="Maximum output rate.")
    parser.add_argument("--deadzone", type=float, default=0.01, help="Minimum axis magnitude to print.")
    parser.add_argument("--show-idle", action="store_true", help="Print every sampled state.")
    parser.add_argument("--list-hid", action="store_true", help="Print all visible HID devices before testing.")
    parser.add_argument("--list-supported", action="store_true", help="Print supported SpaceMouse device specs before testing.")
    parser.add_argument("--scan-only", action="store_true", help="Scan devices and exit without opening SpaceMouse.")
    parser.add_argument("--probe-indices", action="store_true", help="Test every matching device index for input.")
    parser.add_argument("--probe-duration", type=float, default=3.0, help="Seconds to wait on each probed index.")
    args = parser.parse_args()

    # Convert rates into loop delays.
    poll_sleep = 1.0 / args.poll_hz if args.poll_hz > 0 else 0.01
    print_period = 1.0 / args.print_hz if args.print_hz > 0 else 0.0
    deadline = None if args.duration <= 0 else time.monotonic() + args.duration

    # Show installed pyspacemouse version.
    print(f"pyspacemouse version: {pyspacemouse.__version__}")

    # Show supported device specs when requested.
    if args.list_supported:
        print("Supported SpaceMouse devices:")
        for device_name, vendor_id, product_id in pyspacemouse.get_supported_devices():
            print(f"  - {device_name} [VID: {vendor_id:#06x}, PID: {product_id:#06x}]")

    # Show visible HID devices when requested.
    if args.list_hid:
        print("Visible HID devices:")
        for product, manufacturer, vendor_id, product_id in pyspacemouse.get_all_hid_devices():
            product_name = product or "Unknown product"
            manufacturer_name = manufacturer or "Unknown manufacturer"
            print(f"  - {product_name} by {manufacturer_name} [VID: {vendor_id:#06x}, PID: {product_id:#06x}]")

    # Discover supported connected SpaceMouse devices.
    try:
        connected_devices = pyspacemouse.get_connected_devices()
    except RuntimeError as exc:
        print(f"HID scan failed: {exc}", file=sys.stderr)
        print("Linux hint: check hidraw permissions or udev rules for the 3Dconnexion USB device.", file=sys.stderr)
        return 2

    # Print discovery result before opening the device.
    if connected_devices:
        print("Connected SpaceMouse devices:")
        for index, device_name in enumerate(connected_devices):
            print(f"  - [{index}] {device_name}")
    else:
        print("No supported SpaceMouse device detected.", file=sys.stderr)
        print("Try --list-hid to confirm the USB HID device is visible.", file=sys.stderr)
        return 2

    # Stop after discovery when requested.
    if args.scan_only:
        return 0

    # Build candidate indices for receivers with multiple HID interfaces.
    device_name = args.device or connected_devices[0]
    matching_count = sum(1 for name in connected_devices if name == device_name)
    if matching_count == 0:
        print(f"No connected SpaceMouse device named {device_name!r}.", file=sys.stderr)
        return 2

    # Probe every matching device index for live input when requested.
    if args.probe_indices:
        print(f"Probing {device_name} indices 0..{matching_count - 1} for {args.probe_duration:.1f}s each.")
        opened_indices = []
        active_indices = []
        try:
            for device_index in range(matching_count):
                print(f"\nProbe device_index={device_index}")
                try:
                    device = pyspacemouse.open(device=args.device, device_index=device_index, nonblocking=True)
                except (RuntimeError, ValueError) as exc:
                    print(f"  open failed: {exc}", file=sys.stderr)
                    continue

                # Read one opened HID interface for the probe window.
                with device:
                    opened_indices.append(device_index)
                    last_buttons = None
                    last_print = 0.0
                    saw_activity = False
                    probe_deadline = time.monotonic() + args.probe_duration

                    # Watch this index until probe duration expires.
                    while time.monotonic() < probe_deadline:
                        now = time.monotonic()
                        state = device.read()
                        axis_values = [getattr(state, axis) for axis in AXES]
                        buttons = list(state.buttons)
                        moving = any(abs(value) >= args.deadzone for value in axis_values)
                        button_active = any(buttons)
                        button_changed = last_buttons is not None and buttons != last_buttons
                        saw_activity = saw_activity or moving or button_active or button_changed

                        # Print active samples, plus idle samples only when requested.
                        if (args.show_idle or moving or button_active or button_changed) and (
                            button_changed or now - last_print >= print_period
                        ):
                            axes = " ".join(f"{axis}={value:+.3f}" for axis, value in zip(AXES, axis_values))
                            print(f"  t={state.t:>8.3f} {axes} buttons={buttons}", flush=True)
                            last_print = now

                        # Keep previous button state for change detection.
                        last_buttons = buttons
                        time.sleep(poll_sleep)

                # Summarize this probed index.
                if saw_activity:
                    active_indices.append(device_index)
                    print(f"  result: INPUT detected on device_index={device_index}")
                else:
                    print(f"  result: no input detected on device_index={device_index}")
        except KeyboardInterrupt:
            # Treat manual stop as a clean exit.
            print("\nStopped by user.")
            return 0

        # Summarize all probed indices.
        print(f"\nOpened indices: {opened_indices}")
        print(f"Active indices: {active_indices}")
        if active_indices:
            return 0
        return 1 if opened_indices else 2

    # Build candidate index list for normal streaming.
    if args.device_index is None:
        candidate_indices = range(matching_count)
    else:
        candidate_indices = range(args.device_index, args.device_index + 1)

    # Try candidate indices until one HID interface opens.
    device = None
    last_error = None
    for device_index in candidate_indices:
        try:
            device = pyspacemouse.open(device=args.device, device_index=device_index, nonblocking=True)
            print(f"Opened device_index={device_index}: {device.describe_connection()}")
            break
        except (RuntimeError, ValueError) as exc:
            last_error = exc
            print(f"Open failed for device_index={device_index}: {exc}", file=sys.stderr)

    # Stop when no HID interface could be opened.
    if device is None:
        print(f"Failed to open SpaceMouse: {last_error}", file=sys.stderr)
        print("Linux hint: add a udev rule or run with permissions that can read /dev/hidraw*.", file=sys.stderr)
        return 2

    # Stream activity from the opened SpaceMouse.
    try:
        with device:
            print("Move SpaceMouse or press buttons. Ctrl+C stops early.")

            # Track output throttling and observed activity.
            last_buttons = None
            last_print = 0.0
            saw_activity = False

            # Read until duration expires or user interrupts.
            while deadline is None or time.monotonic() < deadline:
                now = time.monotonic()
                state = device.read()
                axis_values = [getattr(state, axis) for axis in AXES]
                buttons = list(state.buttons)
                moving = any(abs(value) >= args.deadzone for value in axis_values)
                button_changed = last_buttons is not None and buttons != last_buttons
                should_print = args.show_idle or moving or button_changed

                # Print state when activity passes deadzone or idle output is enabled.
                if should_print and (button_changed or now - last_print >= print_period):
                    axes = " ".join(f"{axis}={value:+.3f}" for axis, value in zip(AXES, axis_values))
                    print(f"t={state.t:>8.3f} {axes} buttons={buttons}", flush=True)
                    last_print = now

                # Keep activity flag and previous buttons current.
                saw_activity = saw_activity or moving or button_changed
                last_buttons = buttons
                time.sleep(poll_sleep)

            # Report final smoke-test result.
            if saw_activity:
                print("PASS: SpaceMouse produced movement or button activity.")
                return 0

            print("No movement or button activity above deadzone was observed.", file=sys.stderr)
            return 1
    except KeyboardInterrupt:
        # Treat manual stop as a clean exit.
        print("\nStopped by user.")
        return 0


# Run CLI entry point.
if __name__ == "__main__":
    raise SystemExit(main())
