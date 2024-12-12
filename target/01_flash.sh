#!/usr/bin/env bash

set -exo pipefail
cd "$(dirname $0)"
[ -z "$VIRTUAL_ENV" ] && . ../env/bin/activate

esptool.py --chip esp32 erase_flash
esptool.py --baud 460800 write_flash -z 0x1000 ../firmware/ESP32_GENERIC-20240602-v1.23.0.bin