import RPi.GPIO as GPIO
import time
from datetime import datetime
import json

MOTOR_PINS = [17, 18, 27, 22]
CONFIG_FILE = "alarm_config.json"

GPIO.setmode(GPIO.BCM)

for pin in MOTOR_PINS:
    GPIO.setup(pin, GPIO.OUT)
    GPIO.output(pin, GPIO.LOW)

def load_alarm():
    try:
        with open(CONFIG_FILE, "r") as f:
            data = json.load(f)
            return (
                data.get("hour"),
                data.get("minute"),
                data.get("duration"),
                data.get("active", True)
            )
    except Exception as e:
        print("Config load error:", e)
        return None, None, None, False

alarm_triggered = False

print("Alarm system active.")

try:
    while True:
        alarm_hour, alarm_minute, buzz_duration, active = load_alarm()

        if alarm_hour is None:
            time.sleep(5)
            continue

        now = datetime.now()
        h, m = now.hour, now.minute

        print(f"Current: {h:02d}:{m:02d} | Alarm: {alarm_hour:02d}:{alarm_minute:02d} | Active:{active}")

        if h == alarm_hour and m == alarm_minute and not alarm_triggered:
            print("Alarm triggered!")

            while True:
                _, _, _, active = load_alarm()

                if not active:
                    print("Alarm stopped via JSON")
                    break

                for pin in MOTOR_PINS:
                    GPIO.output(pin, GPIO.HIGH)
                time.sleep(4)

                for pin in MOTOR_PINS:
                    GPIO.output(pin, GPIO.LOW)
                time.sleep(2)

            alarm_triggered = True

        if m != alarm_minute:
            alarm_triggered = False

        time.sleep(5)

except KeyboardInterrupt:
    print("Shutting down...")

finally:
    GPIO.cleanup()
