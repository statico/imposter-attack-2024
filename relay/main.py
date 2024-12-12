from time import sleep_ms
import espnow
import json
import network
import ubinascii
import uselect
import sys

wlan = network.WLAN(network.STA_IF)
wlan.active(True)
wlan.disconnect()

e = espnow.ESPNow()
e.active(True)
peer = b"\xbb\xbb\xbb\xbb\xbb\xbb"  # broadcast
e.add_peer(peer)

spoll = uselect.poll()
spoll.register(sys.stdin, uselect.POLLIN)

buf = bytearray(1024)
cursor = 0

print("starting relay")
while True:
    try:
        # Send messages from ESP-NOW to serial
        host, msg = e.recv(timeout_ms=10)
        if msg:
            try:
                message = json.loads(msg)
                mac = ubinascii.hexlify(host).decode()
                print(json.dumps({"host": mac, "message": message}))
            except Exception as err:
                print(json.dumps(f"failed to parse message: {err}"))

        # Send messages from serial to ESP-NOW
        while spoll.poll(0):
            char = sys.stdin.read(1)
            if char == "\n":
                e.send(peer, buf[:cursor])
                print(json.dumps(f"sent {cursor} bytes"))
                cursor = 0
                continue
            else:
                buf[cursor] = ord(char)
                cursor += 1

    except Exception as err:
        print(json.dumps(f"error: {err}"))
