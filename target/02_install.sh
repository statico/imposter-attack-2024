#!/usr/bin/env bash

set -exo pipefail
cd "$(dirname $0)"
[ -z "$VIRTUAL_ENV" ] && . ../env/bin/activate

c="connect /dev/tty.usbserial-0001"
mpremote $c mip install github:peterhinch/micropython_ir/ir_rx
mpremote $c mip install github:mkomon/uota
mpremote $c cp main.py uota.cfg version :/