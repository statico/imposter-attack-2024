#!/usr/bin/env python3

import os
import sys
import time
import subprocess
from serial import Serial
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

"""
This script is a development tool that watches a directory for changes and
automatically copies changed files to a MicroPython board connected over serial.
It also installs any dependencies listed in a "deps" file in the directory using
"mpremote mip install".

Example directory to watch:

    myproject/
      main.py
      deps

Example deps file:

    ssd1306
    github:peterhinch/micropython_ir/ir_rx
    ../my_secrets.py

Then run:

    python devtool.py myproject
"""

# Get device from DEVICE env var, or pick one from /dev
DEVICE = os.environ.get("DEVICE")
if not DEVICE:
    files = os.listdir("/dev")
    for file in files:
        if file.startswith("tty.usbserial") or file.startswith("tty.usbmodem"):
            DEVICE = f"/dev/{file}"
            break
if not DEVICE:
    print("No device found. Set DEVICE env var.")
    sys.exit(1)

# Get baud rate from BAUD env var
BAUD = int(os.environ.get("BAUD") or 460800)


def mpremote(*args, capture=False):
    return subprocess.run(
        ["mpremote", "connect", DEVICE, *args], capture_output=capture
    )


def log(line):
    print(f"\033[96m[devtool] {line}\033[0m")


def check_dependencies(serial, dir):
    if os.environ.get("SKIP_DEPS"):
        return

    deps_file = os.path.join(dir, "deps")
    if not os.path.exists(deps_file):
        log(f"no dependencies to install")
        return

    log("checking dependencies...")
    close_and_wait(serial)

    mpremote("mkdir", "lib", capture=True)  # Kinda mkdir -p

    result = mpremote("ls", "lib", capture=True)
    if not result.stdout:
        log("failed to list lib directory: unknown error")
        return
    if result.returncode != 0:
        msg = result.stdout.decode("latin1").strip()
        log(f"failed to list lib directory: {msg}")
        return

    files = []
    for line in result.stdout.decode("latin1").split("\n"):
        if line and not line.startswith("ls"):
            files.append(line.split()[1])

    for line in open(deps_file, "r"):
        dep = line.strip()
        if not dep:
            continue

        is_missing = True
        is_relative_path = False
        basename = os.path.basename(dep)
        if dep.startswith("."):
            # assume a local dependency
            is_relative_path = True
            is_missing = basename not in files
        elif dep.endswith(".py") or dep.endswith(".mpy"):
            # .py files get copied as is
            is_missing = basename not in files
        elif "/" in dep:
            # assume it's a directory or URL or something
            is_missing = basename + "/" not in files
        else:
            # assume it's micropython-lib package and was installed as a .mpy file
            is_missing = f"{dep}.mpy" not in files

        if is_missing or os.environ.get("FORCE_DEPS"):
            log(f"installing dependency: {dep}")
            if is_relative_path:
                relpath = os.path.join(dir, dep)
                result = mpremote("cp", relpath, f":lib/{basename}")
            else:
                result = mpremote("mip", "install", dep)
            if result.returncode != 0:
                if result.stdout:
                    print(result.stdout.decode("latin1").strip())
                log(f"failed to install dependency: {dep}")
                sys.exit(1)
        else:
            log(f"{basename} exists")

    mpremote("reset")
    open_and_wait(serial)
    return


def close_and_wait(serial):
    serial.close()
    while serial.is_open:
        time.sleep(0.1)
    time.sleep(1)  # serial ports need time to close


def open_and_wait(serial):
    serial.open()
    while not serial.is_open:
        time.sleep(0.1)
    log(f"reading from {serial.name}...")


def main():
    try:
        if len(sys.argv) != 2:
            print(f"Usage: devtool.py <dir>")
            sys.exit(1)

        log(f"DEVICE = {DEVICE}")
        log(f"BAUD = {BAUD}")

        dir = sys.argv[1]
        serial = Serial(DEVICE, BAUD)
        files_to_copy = []
        needs_dependencies = True

        class FileChangeHandler(FileSystemEventHandler):
            def on_modified(self, event):
                if event.is_directory:
                    return
                relpath = os.path.relpath(event.src_path, dir)
                if relpath == "deps":
                    nonlocal needs_dependencies
                    needs_dependencies = True
                else:
                    files_to_copy.append(relpath)

        log(f"watching {dir} for changes")
        event_handler = FileChangeHandler()
        observer = Observer()
        observer.schedule(event_handler, path=dir, recursive=True)
        observer.start()

        for path in os.listdir(dir):
            if path == "deps" or path.endswith(".wav"):
                continue
            log(f"copying {path} to board...")
            full_path = os.path.join(dir, path)
            mpremote("cp", full_path, f":{path}")

        mpremote("reset")

        while True:
            if needs_dependencies:
                needs_dependencies = False
                check_dependencies(serial, dir)

            if len(files_to_copy) > 0:
                close_and_wait(serial)

                for path in files_to_copy:
                    log(f"copying {path} to board...")
                    full_path = os.path.join(dir, path)
                    mpremote("cp", full_path, f":{path}")

                files_to_copy.clear()
                time.sleep(0.5)
                log("resetting...")
                mpremote("reset")
                open_and_wait(serial)

            if serial.is_open and serial.in_waiting:
                line = serial.readline().decode("latin1").strip()
                print(line)
            time.sleep(0.1)

    except OSError as e:
        if e.errno == 6:
            log("device disconnected. exiting...")
        else:
            log(f"error: {e}")
        close_and_wait(serial)
        sys.exit(1)

    except KeyboardInterrupt as e:
        log("exiting...")
        close_and_wait(serial)


if __name__ == "__main__":
    main()
