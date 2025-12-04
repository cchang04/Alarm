import RPi.GPIO as GPIO
import time
from datetime import datetime
import json

# ------------------ SETTINGS ------------------
MOTOR_PINS = [17, 18, 27, 22]
CONFIG_FILE = "alarm_config.json"
# ---------------------------------------------

GPIO.setmode(GPIO.BCM)

for pin in MOTOR_PINS:
    GPIO.setup(pin, GPIO.OUT)
    GPIO.output(pin, GPIO.LOW)

def load_alarm():
    try:
        with open(CONFIG_FILE, "r") as f:
            data = json.load(f)
            return data["hour"], data["minute"], data["duration"]
    except Exception as e:
        print("Config load error:", e)
        return None, None, None

alarm_triggered = False

print("Alarm system running with live JSON updates...")

try:
    while True:
        ALARM_HOUR, ALARM_MINUTE, BUZZ_DURATION = load_alarm()

        if ALARM_HOUR is None:
            time.sleep(5)
            continue

        now = datetime.now()
        h, m = now.hour, now.minute

        print(f"Current: {h:02d}:{m:02d} | Alarm: {ALARM_HOUR:02d}:{ALARM_MINUTE:02d}")

        # Trigger alarm exactly once per minute
        if h == ALARM_HOUR and m == ALARM_MINUTE and not alarm_triggered:
            print("ALARM TRIGGERED")

            for pin in MOTOR_PINS:
                GPIO.output(pin, GPIO.HIGH)

            time.sleep(BUZZ_DURATION)

            for pin in MOTOR_PINS:
                GPIO.output(pin, GPIO.LOW)

            alarm_triggered = True

        # Reset after minute changes
        if m != ALARM_MINUTE:
            alarm_triggered = False

        time.sleep(5)

except KeyboardInterrupt:
    print("Shutting down...")

finally:
    GPIO.cleanup()
