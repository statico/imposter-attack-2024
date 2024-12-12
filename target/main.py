import espnow
import json
import machine
import math
import network
import random
import sys
import ubinascii
import uota  # type: ignore
import network
from ir_rx import IR_RX
from machine import Pin, PWM, reset
from time import sleep_ms, ticks_ms, ticks_diff

print(
    """
    _    _ _               _   _   _             _
   / \\  | (_) ___ _ __    / \\ | |_| |_ __ _  ___| | __
  / _ \\ | | |/ _ | '_ \\  / _ \\| __| __/ _` |/ __| |/ /
 / ___ \\| | |  __| | |  / ___ | |_| || (_| | (__|   <
/_/   \\_|_|_|\\___|_| |_/_/   \\_\\__|\\__\\__,_|\\___|_|\\_\\
"""
)

WIFI_SSID = "mywifi"
WIFI_PASSWORD = "sekrit"

# Display the uota version
with open("version", "r") as f:
    version = f.read().strip()
print(f"version {version}\n")

# Set up the WLAN for ESP-NOW, not IP
wlan = network.WLAN(network.STA_IF)
wlan.active(True)
mac = ubinascii.hexlify(wlan.config("mac"), ":").decode()
wlan.disconnect()

# Receive broadcast messages
e = espnow.ESPNow()
e.active(True)
peer = b"\xbb\xbb\xbb\xbb\xbb\xbb"  # broadcast
e.add_peer(peer)

ir_pin = Pin(5, Pin.IN)
pulse_pwm = PWM(Pin(19), freq=1000, duty=0)
flash_pwm = PWM(Pin(23), freq=1000, duty=0)
imposter_pin = Pin(16, Pin.IN, Pin.PULL_UP)

# Constants
MAX_PULSE_MS = 3000
MAX_FLASH_MS = 300

# Params sent by server
state = "boot"
game_length = 60
respawn_delay_min = 3000
respawn_delay_max = 7000
target_lifetime = 4000
regular_target_health = 1
boss_target_health = 10

# Internal state
pulse_life = 0
flash_life = 0
target_life = 0
next_event_ms = 0
last_ms = 0
last_hit_ms = 0
hp = 0


def connect_wifi(hostname=None):
    if wlan.isconnected():
        print(f"already connected with IP {wlan.ifconfig()[0]}")
        return
    print(f"mac address: {mac}")
    print("connecting to wifi...")
    wlan.active(True)
    if hostname is None:
        hostname = f"esp32-{mac}"
    wlan.config(dhcp_hostname=hostname)
    wlan.connect(WIFI_SSID, WIFI_PASSWORD)
    while not wlan.isconnected():
        print(".", end="")
        pass
    print("\nconnected with IP", wlan.ifconfig()[0])


def is_imposter():
    return imposter_pin.value() == 0


def blink(count=1, ms=400):
    for _ in range(count):
        pulse_pwm.duty(0)
        flash_pwm.duty(1023)
        sleep_ms(ms)

        pulse_pwm.duty(1023)
        flash_pwm.duty(0)
        sleep_ms(ms)

    pulse_pwm.duty(0)
    flash_pwm.duty(0)


def handle_update(obj):
    if "update" in obj:
        blink(3, 200)
        print("update requested")
        connect_wifi()
        try:
            if uota.check_for_updates():
                blink(5, 150)
                print("update available")
                uota.install_new_firmware()
            else:
                print("no update available")
        except Exception as err:
            print("update failed")
            print(err)
        machine.reset()

    global state, game_length, respawn_delay_min, respawn_delay_max, target_lifetime, regular_target_health, boss_target_health

    old_state = state

    if "state" in obj:
        state = str(obj["state"])
    if "game_length" in obj:
        game_length = int(obj["game_length"])
    if "respawn_delay_min" in obj:
        respawn_delay_min = int(obj["respawn_delay_min"])
    if "respawn_delay_max" in obj:
        respawn_delay_max = int(obj["respawn_delay_max"])
    if "target_lifetime" in obj:
        target_lifetime = int(obj["target_lifetime"])
    if "regular_target_health" in obj:
        regular_target_health = int(obj["regular_target_health"])
    if "boss_target_health" in obj:
        boss_target_health = int(obj["boss_target_health"])

    print(
        f"ST={state} GL={game_length} RSMin={respawn_delay_min} RSMax={respawn_delay_max} TL={target_lifetime} RHP={regular_target_health} BHP={boss_target_health}"
    )

    if old_state != state:
        handle_state_change()


def send_event(type):
    e.send(peer, json.dumps({"event": type, "millis": ticks_ms()}), True)


def send_status():
    e.send(
        peer,
        json.dumps({"state": state, "millis": ticks_ms(), "version": version}),
        True,
    )


def handle_hit():
    global hp, last_hit_ms, target_life, flash_life

    now = ticks_ms()
    if last_hit_ms + 50 > now:
        return  # Add some delay
    last_hit_ms = now
    print(f"handling hit {now}")

    if state == "game":
        if target_life > 0:
            flash_life = MAX_FLASH_MS
            if hp > 0:
                hp -= 1
            if hp == 0:
                target_life = 0
                if is_imposter():
                    send_event("boss-death")
                else:
                    send_event("regular-death")
                schedule_next_event()
    elif state == "test":
        flash_life = MAX_FLASH_MS


def schedule_next_event(initial=False):
    global next_event_ms
    delay = 1000
    if state == "boot":
        delay = MAX_PULSE_MS
    elif state == "idle":
        if initial:
            delay = random.randint(0, 10000)
        else:
            delay = random.randint(5000, 10000)
    elif state == "game":
        multiplier = 2 if is_imposter() else 1
        low = 0 if initial else respawn_delay_min * multiplier
        high = respawn_delay_max if initial else respawn_delay_max * multiplier
        delay = random.randint(low, high)
    elif state == "end":
        delay = 0
    elif state == "test":
        delay = 2000
    next_event_ms = ticks_ms() + delay


def handle_state_change():
    global state, target_life, pulse_life, flash_life
    print(f"state changed to {state}")
    if state == "idle":
        schedule_next_event(True)
    elif state == "end":
        target_life = 0
        pulse_life = 0
        flash_life = 0
        schedule_next_event()
    elif state == "ready":
        target_life = 0
        pulse_life = 1000
        flash_life = 0
    elif state == "game":
        schedule_next_event(True)


class IR_GET(IR_RX):
    def __init__(self, pin):
        super().__init__(pin, 100, 100, lambda *_: None)
        self.data = None

    def decode(self, _):
        burst_len = self.edge - 1  # Possible length of burst
        burst = []
        for i in range(burst_len):
            dt = ticks_diff(self._times[i + 1], self._times[i])
            if i > 0 and dt > 10000:  # Reached gap between repeats
                break
            burst.append(dt)
        burst_len = len(burst)  # Actual length

        global state
        if state == "boot":
            handle_hit()
            self.data = burst
            self.do_callback(0, 0, 0)
            return

        # print(f'burst[0]={burst[0]} burst_len={burst_len}')

        # TONS of fiddling to get the laser gun settings working
        bits = ""
        if burst[0] > 1200 and burst[0] < 1800:
            # Laser gun
            for i, value in enumerate(burst):
                # print('{:03d} {:5d}'.format(i, value))
                if i == 0:
                    continue
                if i % 2 == 1:
                    # print(f"{i:03d} {value} {value > 750}")
                    bits += "1" if value > 750 else "0"
        else:
            # Wand or anything else
            for i, value in enumerate(burst):
                bits += "1" if value > 500 else "0"
                # print(f"{i:03d} {value} {value > 500}")

        def separate(binary_string, chunk_size=4):
            return " ".join(
                [
                    binary_string[i : i + chunk_size]
                    for i in range(0, len(binary_string), chunk_size)
                ]
            )

        # print(separate(bits))

        # Wand is acting strangely. Trim any leading 10+
        bits.replace("1" + "0" * (len(bits) - len(bits.lstrip("0"))), "", 1)

        if len(bits) == 20 and bits[:8] == "00001111":
            print("hit (pistol)")
            handle_hit()
        elif len(bits) >= 12 and bits[:12] == "100101010101":
            print("hit (wand)")
            handle_hit()
        else:
            print(f"unknown IR signal: {separate(bits)}")
            e.send(peer, json.dumps({"bits": bits}), True)

        self.data = burst
        self.do_callback(0, 0, 0)


ir = IR_GET(ir_pin)

print("starting alien attack target...")
print(f"MAC: {mac}")
print(f"state = {state}")
blink(2)

try:
    if is_imposter():
        blink(20, 75)

    while True:
        now = ticks_ms()
        delta = now - last_ms

        # Receive any new state
        _, msg = e.recv(timeout_ms=10)
        if msg:
            try:
                handle_update(json.loads(msg))
            except Exception as err:
                print("invalid message:", msg)
                print(err)

        # Check if target has died
        target_expired = target_life > 0 and target_life < delta
        flash_life = max(0, flash_life - delta)
        pulse_life = max(0, pulse_life - delta)
        target_life = max(0, target_life - delta)

        # Update pulse LED
        pulse_value = math.sin(pulse_life / (MAX_PULSE_MS / math.pi))
        if target_life > 0:
            if target_life > 1200:
                pulse_pwm.duty(1023)
            elif target_life > 1000:
                pulse_pwm.duty(0)
            elif target_life > 800:
                pulse_pwm.duty(1023)
            elif target_life > 600:
                pulse_pwm.duty(0)
            elif target_life > 400:
                pulse_pwm.duty(1023)
            elif target_life > 200:
                pulse_pwm.duty(0)
            else:
                pulse_pwm.duty(1023)
        else:
            pulse_pwm.duty(int(pulse_value * 1023))

        # Update flash LED
        flash_value = flash_life / MAX_FLASH_MS
        flash_pwm.duty(int(flash_value * 1023))

        # Do state-specific actions
        if state == "boot":
            if now > next_event_ms:
                print("firing boot event")
                pulse_life = MAX_PULSE_MS
                flash_life = MAX_FLASH_MS
                send_status()
                schedule_next_event()
        elif state == "idle":
            if now > next_event_ms:
                print("firing idle event")
                pulse_life = MAX_PULSE_MS
                send_status()
                schedule_next_event()
        elif state == "game":
            if target_expired:
                schedule_next_event()
            elif now > next_event_ms:
                next_event_ms = now + 1000 * 60 * 60  # Infinity
                if is_imposter():
                    target_life = target_lifetime * 2
                    hp = boss_target_health
                    send_event("boss-appear")
                else:
                    target_life = target_lifetime
                    hp = regular_target_health
        elif state == "test":
            if now > next_event_ms:
                pulse_life = MAX_PULSE_MS
                send_status()
                schedule_next_event()

        last_ms = now
        sleep_ms(20)


except Exception as err:
    e.send(peer, json.dumps({"error": str(err)}), True)
    sys.print_exception(e)  # type: ignore
    sleep_ms(1000)
    reset()
