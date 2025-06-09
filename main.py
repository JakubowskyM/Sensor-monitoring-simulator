import time
from datetime import datetime
import sensors as s
import logger as l

# Tworzenie instancji loggera z pliku konfiguracyjnego
logger = l.Logger(config_path='Data/config.json')
logger.start()  # Rozpoczęcie logowania (otwarcie nowego pliku)

# Inicjalizacja czujników
tS = s.TemperatureSensor(sensor_id=1, name="TemperatureSensor", frequency=10)
hS = s.HumiditySensor(sensor_id=2, name="HumiditySensor", frequency=10)
pS = s.PressureSensor(sensor_id=3, name="PressureSensor", frequency=10)
lS = s.LightSensor(sensor_id=4, name="LightSensor", frequency=10)

# Rejestracja callbacków, które będą zapisywać odczytane dane
tS.register_callback(logger.log_reading)
hS.register_callback(logger.log_reading)
pS.register_callback(logger.log_reading)
lS.register_callback(logger.log_reading)

# Lista wszystkich czujników
sensors = [tS, hS, pS, lS]

# Rejestrowanie czasu ostatniego odczytu dla każdego czujnika
last_read_times = {sensor: 0 for sensor in sensors}

try:
    # Główna pętla programu - odczyt czujników
    while True:
        current_time = time.time()

        for sensor in sensors:
            if current_time - last_read_times[sensor] >= sensor.frequency:
                # Wartość czujnika jest odczytywana i zapisuje się przez callback
                value = sensor.read_value()
                print(f"[{time.strftime('%H:%M:%S')}] {sensor.name} ({sensor.unit}): {value:.2f}")
                last_read_times[sensor] = current_time  # Aktualizacja czasu ostatniego odczytu

        # Czas oczekiwania przed kolejnym odczytem
        time.sleep(0.1)

except KeyboardInterrupt:
    # Obsługa zakończenia programu
    print("\nZakończono działanie programu.")
    logger.stop()  # Zatrzymanie loggera i zapisanie pozostałych danych
