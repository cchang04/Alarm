#!/usr/bin/env python3
import asyncio
from bleak import BleakClient, BleakScanner
import RPi.GPIO as GPIO
from RPLCD.i2c import CharLCD
from datetime import datetime, timedelta
import time

# LCD setup
lcd = CharLCD('PCF8574', 0x27, cols=20, rows=4)
lcd.clear()
time.sleep(0.1)  # Ensure LCD starts clean

FEATHER_NAME = "FeatherBattery"
UART_RX_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"
UART_TX_UUID = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"

client = None
battery_percent = "--"
connected = False

# Clock variables
clock_time_offset = 0
alarm_hour = 7
alarm_min = 0

last_alarm_time = None

mode = "normal"
previous_mode = "normal"

BACKLIGHT_TIMEOUT = 300
last_input_time = time.time()
backlight_on = True
vibration_triggered_today = False

# GPIO setup
BTN_SNOOZE = 17
BTN_HOUR = 27
BTN_MIN = 22

GPIO.setmode(GPIO.BCM)
GPIO.setup(BTN_SNOOZE, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(BTN_HOUR, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(BTN_MIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

# Functions
def button_pressed(pin):
    return GPIO.input(pin) == GPIO.LOW

def held_for(pin, duration):
    start = time.time()
    while button_pressed(pin):
        if time.time() - start >= duration:
            return True
        time.sleep(0.02)
    return False

def both_buttons_held(p1, p2, duration):
    start = time.time()
    while button_pressed(p1) and button_pressed(p2):
        if time.time() - start >= duration:
            return True
        time.sleep(0.02)
    return False

def get_display_time():
    real_now = datetime.now()
    adjusted = real_now + timedelta(seconds=clock_time_offset)
    return adjusted

async def send_vibration_command(cmd):
    global client
    try:
        if client and await client.is_connected():
            await client.write_gatt_char(UART_TX_UUID, cmd.encode())
            print("Sent:", cmd)
        else:
            print("ERROR: Feather not connected.")
    except Exception as e:
        print("BLE Command Error:", e)

# BLE notification handler
async def notification_handler(sender, data):
    global battery_percent, connected
    connected = True
    try:
        text = data.decode().strip()
        if text.startswith("BATT:"):
            battery_percent = int(text.replace("BATT:", "").replace("%", ""))
    except:
        pass

# BLE connection loop
async def connect_loop():
    global client, connected
    while True:
        print("Scanning for Feather...")
        device = await BleakScanner.find_device_by_filter(
            lambda d, ad: FEATHER_NAME in (ad.local_name or "")
        )
        if device is None:
            connected = False
            await asyncio.sleep(2)
            continue

        try:
            client = BleakClient(device)
            await client.connect()
            connected = True
            await client.start_notify(UART_RX_UUID, notification_handler)

            while await client.is_connected():
                await asyncio.sleep(0.2)

        except Exception as e:
            print("BLE Error:", e)

        connected = False
        await asyncio.sleep(2)

async def lcd_loop():
    global mode, previous_mode, alarm_hour, alarm_min

    # Store previous screen content (char-by-char)
    prev_chars = [[" "] * 20 for _ in range(4)]

    while True:
        try:
            if mode == "time_set":
                t = get_display_time()
                new_lines = [
                    "** TIME SET MODE ** ".ljust(20),
                    f"Time: {t:%I:%M %p}".ljust(20),
                    "Use H/M to adjust".ljust(20),
                    "Hold H+M: exit".ljust(20)
                ]

            elif mode == "alarm_set":
                new_lines = [
                    "** ALARM SET MODE **".ljust(20),
                    f"Alarm: {alarm_hour:02d}:{alarm_min:02d}".ljust(20),
                    "Use H/M to adjust".ljust(20),
                    "Hold Snooze: exit".ljust(20)
                ]

            else:  # normal mode
                t = get_display_time()
                safe_batt = str(battery_percent)
                safe_status = "Connected" if connected else "Disconnected"

                new_lines = [
                    f"Time: {t:%I:%M:%S %p}".ljust(20),
                    f"Date: {t:%m-%d-%Y}".ljust(20),
                    f"Battery: {safe_batt}%".ljust(20),
                    f"Status: {safe_status}".ljust(20)
                ]

            if mode != previous_mode:
                lcd.clear()
                prev_chars = [[" "] * 20 for _ in range(4)]
                previous_mode = mode

            for row in range(4):
                for col in range(20):
                    new_c = new_lines[row][col]
                    if prev_chars[row][col] != new_c:
                        lcd.cursor_pos = (row, col)
                        lcd.write_string(new_c)
                        prev_chars[row][col] = new_c

        except Exception as e:
            print("LCD ERROR:", e)

        await asyncio.sleep(0.1)

async def button_loop():
    global mode, alarm_hour, alarm_min, last_input_time

    while True:
        if any(button_pressed(p) for p in [BTN_SNOOZE, BTN_MIN, BTN_HOUR]):
            last_input_time = time.time()

        # Toggle time set mode
        if both_buttons_held(BTN_HOUR, BTN_MIN, 3):
            mode = "time_set" if mode != "time_set" else "normal"
            await asyncio.sleep(0.5)

        # Toggle alarm set mode
        if held_for(BTN_SNOOZE, 3):
            mode = "alarm_set" if mode != "alarm_set" else "normal"
            await asyncio.sleep(0.5)

        # Time adjustments
        if mode == "time_set":
            if button_pressed(BTN_HOUR):
                clock_time_offset += 3600
                await asyncio.sleep(0.3)

            if button_pressed(BTN_MIN):
                clock_time_offset += 60
                await asyncio.sleep(0.3)

        # Alarm adjustments
        if mode == "alarm_set":
            if button_pressed(BTN_HOUR):
                alarm_hour = (alarm_hour + 1) % 24
                await asyncio.sleep(0.3)

            if button_pressed(BTN_MIN):
                alarm_min = (alarm_min + 1) % 60
                await asyncio.sleep(0.3)

        await asyncio.sleep(0.02)

async def check_alarm():
    global last_alarm_time

    now = get_display_time()
    hour = now.hour
    minute = now.minute

    if button_pressed(BTN_MIN):
        await send_vibration_command("STOP")
        # Block alarm for this minute only
        last_alarm_time = (hour, minute)
        return

    if last_alarm_time == (hour, minute) and button_pressed(BTN_SNOOZE):
        await send_vibration_command("SNOOZE")
        last_alarm_time = None  # allow snooze retrigger
        return

    if (hour, minute) == (alarm_hour, alarm_min) and last_alarm_time != (hour, minute):
        print("ALARM TIME ? VIB_ON")
        await send_vibration_command("VIB_ON")
        last_alarm_time = (hour, minute)

async def alarm_loop():
    while True:
        await check_alarm()
        await asyncio.sleep(1)

async def main():
    await asyncio.gather(
        connect_loop(),
        lcd_loop(),
        button_loop(),
        alarm_loop()
    )

asyncio.run(main())
