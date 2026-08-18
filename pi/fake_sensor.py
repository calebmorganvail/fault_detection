# Stand in for a real Pi so the project can be demoed without hardware.
#
# Sends the same JSON that sensor.py sends, but the temperature is
# generated instead of read from a DHT22.
#
# Run two of these to exercise the live sensors tab:
#   SENSOR_ID=A python3 fake_sensor.py
#   SENSOR_ID=B JITTER=0.4 python3 fake_sensor.py
#
# JITTER adds a random delay before each POST. That is what the two Pis
# looked like on the real network, and it is what the server side
# synchronizer exists to handle.

import math
import os
import random
import time

import requests

SERVER_URL = os.environ.get("SERVER_URL", "http://localhost:5001/api/reading")
SENSOR_ID = os.environ.get("SENSOR_ID", "A")
INTERVAL = 1

# Degrees C the readings drift around, and how far off this sensor is.
BASE_TEMP_C = float(os.environ.get("BASE_TEMP_C", 21.1))
OFFSET_C = float(os.environ.get("OFFSET_C", 0.0))
JITTER = float(os.environ.get("JITTER", 0.0))

print(f"Fake sensor {SENSOR_ID} sending to {SERVER_URL}")

step = 0

while True:
    # A slow sine wave plus a little noise, so the chart looks alive.
    temp_c = BASE_TEMP_C + OFFSET_C + math.sin(step / 15) + random.uniform(-0.2, 0.2)
    humidity = 50 + math.sin(step / 20) * 5

    if JITTER:
        time.sleep(random.uniform(0, JITTER))

    try:
        data = {
            "sensor_id": SENSOR_ID,
            "temp_c": round(temp_c, 2),
            "humidity": round(humidity, 2),
        }
        requests.post(SERVER_URL, json=data)
        print(f"Sent: {data['temp_c']}C, {data['humidity']}%")
    except Exception as e:
        print(f"Error: {e}")

    step += 1
    time.sleep(INTERVAL)
