import RPi.GPIO as GPIO
import time
from datetime import datetime
import json

motor_pins = [17, 18, 27, 22]
config_file = "alarm_config.json"

GPIO.setmode(GPIO.BCM)

for pin in motor_pins:
    GPIO.setup(pin, GPIO.OUT)
    GPIO.output(pin, GPIO.LOW)

def load_alarm():
    try:
        with open(config_file, "r") as f:
            data = json.load(f)
            return (
                data.get("hour"),
                data.get("minute"),
                data.get("active", True)
            )
    except:
        return None, None, False

def save_active_state(state):
    try:
        with open(config_file, "r") as f:
            data = json.load(f)
        data["active"] = state
        with open(config_file, "w") as f:
            json.dump(data, f, indent=4)
    except:
        pass

alarm_triggered = False

print("Alarm system running...")

try:
    while True:
        alarm_hour, alarm_minute, active = load_alarm()

        if alarm_hour is None:
            time.sleep(5)
            continue

        now = datetime.now()
        h, m = now.hour, now.minute

        print(f"Current: {h:02d}:{m:02d} | Alarm: {alarm_hour:02d}:{alarm_minute:02d} | Active:{active}")

        if h == alarm_hour and m == alarm_minute and not alarm_triggered:
            print("Alarm triggered!")

            while True:
                _, _, active = load_alarm()

                if not active:
                    print("Alarm stopped")
                    break

                for pin in motor_pins:
                    GPIO.output(pin, GPIO.HIGH)
                time.sleep(4)

                for pin in motor_pins:
                    GPIO.output(pin, GPIO.LOW)
                time.sleep(2)

            alarm_triggered = True

        time.sleep(5)

except KeyboardInterrupt:
    print("Shutting down")

    for pin in motor_pins:
        GPIO.output(pin, GPIO.LOW)

    save_active_state(False)

finally:
    GPIO.cleanup()
    print("GPIO cleaned up")
