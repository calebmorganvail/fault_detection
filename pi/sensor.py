# Reads a DHT22 sensor and sends the data to the server.
#
# Setup (on the Pi):
#   sudo apt-get install libgpiod2
#   uv pip install -r pyproject.toml
#
# Get the server IP (on mac):
#   ipconfig getifaddr en0
#
# Run it (set SENSOR_ID to A on one Pi and B on the other):
#   SENSOR_ID=A SERVER_URL=http://<laptop-ip>:5001/api/reading python3 sensor.py

import os
import time

import adafruit_dht
import board
import requests

SERVER_URL = os.environ.get("SERVER_URL", "http://192.168.0.30:5001/api/reading")
SENSOR_ID = os.environ.get("SENSOR_ID", "A")
SENSOR_PIN = board.D4
INTERVAL = 1

sensor = adafruit_dht.DHT22(SENSOR_PIN)

print(f"Sensor {SENSOR_ID} sending to {SERVER_URL}")

while True:
    try:
        temp_c = sensor.temperature
        humidity = sensor.humidity

        if temp_c is not None:
            data = {"sensor_id": SENSOR_ID, "temp_c": temp_c, "humidity": humidity}
            requests.post(SERVER_URL, json=data)
            print(f"Sent: {temp_c}C, {humidity}%")
        else:
            print("Sensor returned None, skipping")

    except Exception as e:
        print(f"Error: {e}")

    time.sleep(INTERVAL)
