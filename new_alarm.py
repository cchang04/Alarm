#!/usr/bin/env python3
import asyncio
from bleak import BleakClient, BleakScanner
import RPi.GPIO as GPIO
from RPLCD.i2c import CharLCD
from datetime import datetime, timedelta
import time

# LCD setup
lcd = CharLCD('PCF8574', 0x27, cols=20, rows=4)

FEATHER_NAME = "FeatherBattery"
UART_SERVICE_UUID = "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
UART_RX_UUID      = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"
client = None
battery_percent = "--"
connected = False

#Clock Variables
clock_time_offset = 0
alarm_hour = 7
alarm_min = 0

mode = "normal"
mode_enter_time = 0
BACKLIGHT_TIMEOUT = 300
last_input_time = time.time()
backlight_on = True
vibration_triggered_today = False

#GPIO Setup
BTN_SNOOZE = 17
BTN_HOUR = 27
BTN_MIN = 22

GPIO.setmode(GPIO.BCM)
GPIO.setup(BTN_SNOOZE, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(BTN_HOUR, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(BTN_MIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

#Button Functions
def button_pressed(pin):
    return GPIO.input(pin) == GPIO.LOW

def held_for(pin, duration):
    start = time.time()
    while button_pressed(pin):
        if time.time() - start >= duration:
            return True
        time.sleep(0.02)
    return False

def both_buttons_held(pin1, pin2, duration):
    start = time.time()
    while button_pressed(pin1) and button_pressed(pin2):
        if time.time() - start >= duration:
            return True
        time.sleep(0.02)
    return False

#Time functions
def get_display_time():
    real_now = datetime.now()
    adjusted = real_now + timedelta(seconds=clock_time_offset)
    return adjusted

def adjust_time(hours=0, mins=0):
    global clock_time_offset
    now = datetime.now()
    new_time = now + timedelta(seconds=clock_time_offset) + timedelta(hours=hours, minutes=mins)
    diff = new_time - now
    clock_time_offset = diff.total_seconds()

def backlight(enable: bool):
    global lcd, backlight_on
    try:
        if enable:
            lcd.backlight_enabled = True
        else:
            lcd.backlight_enabled = False
        backlight_on = enable
    except Exception as e:
        print("Backlight control error:", e)

async def notification_handler(sender, data):
    global battery_percent, connected
    connected = True
  
    try:
        text = data.decode().strip()  # e.g., "BATT:47%"
        if text.startswith("BATT:"):
            value = text.replace("BATT:", "").replace("%", "")
            battery_percent = int(value)
    except Exception as e:
        print("Parse error:", e)

async def connect_loop():
    global connected, client
    client = None
    was_connected = False

    while True:
        print("Scanning for Feather...")
        device = await BleakScanner.find_device_by_filter(
            lambda d, ad: FEATHER_NAME in (ad.local_name or "")
        )

        if device is None:
            connected = False if not was_connected else connected
            await asyncio.sleep(2)
            continue

        print("Found:", device.address)

        try:
            client = BleakClient(device)
            await client.connect()
            print("Connected!")
            connected = True
            was_connected = True
            await client.start_notify(UART_RX_UUID, notification_handler)

            # Stay here until disconnect
            while await client.is_connected():
                await asyncio.sleep(0.2)
            print("Lost connection!")
          
        except Exception as e:

            print("BLE Error:", e)

        # If it Was connected before, mark it disconnected now
        connected = False
        await asyncio.sleep(2)

async def lcd_loop():
    global mode, alarm_hour, alarm_min
    while True:
        lcd.cursor_pos = (0, 0)

        #Time set mode
        if mode == "time_set":
            lcd.write_string("** TIME SET MODE ** ".ljust(20))
            t = get_display_time()
            lcd.cursor_pos = (1, 0)
            lcd.write_string(f"Time: {t:%I:%M %p}".ljust(20))
            lcd.cursor_pos = (2, 0)
            lcd.write_string("Use H/M to adjust".ljust(20))
            lcd.cursor_pos = (3, 0)
            lcd.write_string("Hold H+M: exit".ljust(20))

        #alarm set mode
        elif mode == "alarm_set":
            lcd.write_string("** ALARM SET MODE **".ljust(20))
            lcd.cursor_pos = (1, 0)
            lcd.write_string(f"Alarm: {alarm_hour:02d}:{alarm_min:02d}".ljust(20))
            lcd.cursor_pos = (2, 0)
            lcd.write_string("Use H/M to adjust".ljust(20))
            lcd.cursor_pos = (3, 0)
            lcd.write_string("Hold Snooze: exit".ljust(20))
          
        #mornal mode
        else:
            t = get_display_time()
            lcd.write_string(f"Time: {t:%I:%M:%S %p}".ljust(20))
            lcd.cursor_pos = (1, 0)
            lcd.write_string(f"Date: {t:%m-%d-%Y}".ljust(20))
            lcd.cursor_pos = (2, 0)
            safe_batt = str(battery_percent)
            lcd.write_string(f"Battery: {safe_batt}%".ljust(20))
            lcd.cursor_pos = (3, 0)
            stat = "Connected" if connected else "Disconnected"
            lcd.write_string(f"Status: {stat}".ljust(20))
        await asyncio.sleep(0.15)

async def button_loop():
    global mode, alarm_hour, alarm_min, last_input_time
    while True:

        #if any button is pressed, turn display back on
        if(button_pressed(BTN_SNOOZE) or button_pressed(BTN_MIN) or button_pressed(BTN_HOUR)):
            last_input_time = time.time()
            if not backlight_on:
                backlight(True)

        #Toggle time set mode
        if both_buttons_held(BTN_HOUR, BTN_MIN, 3):
            mode = "time_set" if mode != "time_set" else "normal"
            await asyncio.sleep(0.5)

        #Toggle alarm set mode
        if held_for(BTN_SNOOZE, 3):
            mode = "alarm_set" if mode != "alarm_set" else "normal"
            await asyncio.sleep(0.5)

        #time set adjustments
        if mode == "time_set":
            if button_pressed(BTN_HOUR):
                adjust_time(hours=1)
                await asyncio.sleep(0.3)

            if button_pressed(BTN_MIN):
                adjust_time(mins=1)
                await asyncio.sleep(0.3)

        #Alarm set adjustements
        if mode == "alarm_set":
            if button_pressed(BTN_HOUR):
                alarm_hour = (alarm_hour + 1) % 24
                await asyncio.sleep(0.3)

            if button_pressed(BTN_MIN):
                alarm_min = (alarm_min + 1) % 60
                await asyncio.sleep(0.3)

        if backlight_on and (time.time() - last_input_time > BACKLIGHT_TIMEOUT):
             backlight(False)

        await asyncio.sleep(0.02)

async def send_vibration_command(command):
    global client
    try:
        if client and await client.is_connected():
            await client.write_gatt_char(
                "6E400002-B5A3-F393-E0A9-E50E24DCCA9E",  # UART TX (Pi ? Feather)
                command.encode()
            )
            print(f"Sent vibration command: {command}")
          
        else:
            print("Cannot send vibration command - BLE not connected.")
    except Exception as e:
        print("Error sending vibration command:", e)

async def check_alarm():
    global vibration_triggered_today

    now = get_display_time()
    hour = now.hour
    minute = now.minute

    if button_pressed(BTN_MIN):
        await send_vibration_command("STOP")
        vibration_triggered_today = False
        return

    if vibration_triggered_today and button_pressed(BTN_SNOOZE):
        await send_vibration_command("SNOOZE")
        vibration_triggered_today = False
        return

    if hour == 0 and minute == 0:
        vibration_triggered_today = False

    if hour == alarm_hour and minute == alarm_min and not vibration_triggered_today:
        print("ALARM TIME → VIB_ON")
        await send_vibration_command("VIB_ON")
        vibration_triggered_today = True

async def alarm_loop():
    while True:

        if button_pressed(BTN_MIN):
            await send_vibration_command("STOP")
            global vibration_triggered_today
            vibration_triggered_today = False
            await asyncio.sleep(1)
            continue

        await check_alarm()
        await asyncio.sleep(1)  # check every second

async def main():
    await asyncio.gather(connect_loop(), lcd_loop(), button_loop(), alarm_loop())

asyncio.run(main())
