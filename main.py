import time
import sensors as s

tS = s.TemperatureSensor(sensor_id=1, name="TempSensor", frequency=10)
hS = s.HumiditySensor(sensor_id=2, name="HumiditySensor", frequency=10)
pS = s.PressureSensor(sensor_id=3, name="PressureSensor", frequency=10)
lS = s.LightSensor(sensor_id=4, name="LightSensor", frequency=10)

sensors = [tS, hS, pS, lS]
last_read_times = {sensor: 0 for sensor in sensors}

try:
    while True:
        current_time = time.time()

        for sensor in sensors:
            if current_time - last_read_times[sensor] >= sensor.frequency:
                value = sensor.read_value()
                print(f"[{time.strftime('%H:%M:%S')}] {sensor.name} ({sensor.unit}): {value:.2f}")
                last_read_times[sensor] = current_time

        time.sleep(0.1)

except KeyboardInterrupt:
    print("\nZakończono działanie programu.")
