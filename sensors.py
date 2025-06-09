import random
import time
from datetime import datetime
from typing import Callable


class Sensor:
    def __init__(self, sensor_id, name, unit, min_value, max_value, frequency=1):
        self.sensor_id = sensor_id
        self.name = name
        self.unit = unit
        self.min_value = min_value
        self.max_value = max_value
        self.frequency = frequency
        self.active = True
        self.last_value = None
        self.callbacks = []  # Lista callbacków

    def register_callback(self, callback: Callable):
        """Rejestracja callbacku logującego"""
        self.callbacks.append(callback)

    def _notify_callbacks(self, timestamp: datetime, value: float):
        """Powiadamianie wszystkich zarejestrowanych callbacków"""
        for callback in self.callbacks:
            callback(self.sensor_id, timestamp, value, self.unit)

    def read_value(self):
        """Czytanie wartości czujnika (do nadpisania w klasach dziedziczących)"""
        if not self.active:
            raise Exception(f"Czujnik {self.name} jest wyłączony.")

        # Generowanie wartości
        value = random.uniform(self.min_value, self.max_value)
        timestamp = datetime.now()
        self.last_value = value
        self._notify_callbacks(timestamp, value)  # Powiadomienie callbacków po odczycie
        return value

    def calibrate(self, calibration_factor):
        """Kalibracja czujnika"""
        if self.last_value is None:
            self.read_value()
        self.last_value *= calibration_factor
        return self.last_value

    def get_last_value(self):
        """Zwraca ostatnią wartość czujnika"""
        if self.last_value is None:
            return self.read_value()
        return self.last_value

    def start(self):
        """Włącza czujnik"""
        self.active = True

    def stop(self):
        """Wyłącza czujnik"""
        self.active = False

    def __str__(self):
        return f"Sensor(id={self.sensor_id}, name={self.name}, unit={self.unit})"


class TemperatureSensor(Sensor):
    def __init__(self, sensor_id, name, unit='°C', frequency=5):
        super().__init__(sensor_id, name, unit, -20, 50, frequency)

    def read_value(self):
        """Czytanie wartości z czujnika temperatury z uwzględnieniem pory dnia"""
        if not self.active:
            raise Exception(f"Czujnik {self.name} jest wyłączony.")

        current_hour = int(time.strftime("%H", time.localtime()))

        # Dostosowanie zakresu w zależności od godziny
        if self.last_value is None:
            if 6 <= current_hour < 18:
                value = random.uniform(15, self.max_value)
            else:
                value = random.uniform(self.min_value, 10)
        else:
            lower_bound = max(self.min_value, self.last_value - 1)
            upper_bound = min(self.max_value, self.last_value + 1)
            value = random.uniform(lower_bound, upper_bound)

        timestamp = datetime.now()
        self.last_value = value
        self._notify_callbacks(timestamp, value)  # Powiadomienie callbacków
        return value


class HumiditySensor(Sensor):
    def __init__(self, sensor_id, name, unit='%', frequency=5):
        super().__init__(sensor_id, name, unit, 0, 100, frequency)

    def read_value(self):
        """Czytanie wartości z czujnika wilgotności"""
        if not self.active:
            raise Exception(f"Czujnik {self.name} jest wyłączony.")

        if self.last_value is None:
            value = random.uniform(40, 60)
        else:
            lower_bound = max(self.min_value, self.last_value - 1)
            upper_bound = min(self.max_value, self.last_value + 1)
            value = random.uniform(lower_bound, upper_bound)

        timestamp = datetime.now()
        self.last_value = value
        self._notify_callbacks(timestamp, value)  # Powiadomienie callbacków
        return value


class PressureSensor(Sensor):
    def __init__(self, sensor_id, name, unit='hPa', frequency=5):
        super().__init__(sensor_id, name, unit, 950, 1050, frequency)

    def read_value(self):
        """Czytanie wartości z czujnika ciśnienia"""
        if not self.active:
            raise Exception(f"Czujnik {self.name} jest wyłączony.")

        if self.last_value is None:
            value = random.uniform(990, 1010)
        else:
            lower_bound = max(self.min_value, self.last_value - 1)
            upper_bound = min(self.max_value, self.last_value + 1)
            value = random.uniform(lower_bound, upper_bound)

        timestamp = datetime.now()
        self.last_value = value
        self._notify_callbacks(timestamp, value)  # Powiadomienie callbacków
        return value


class LightSensor(Sensor):
    def __init__(self, sensor_id, name, unit='lux', frequency=5):
        super().__init__(sensor_id, name, unit, 0, 1000, frequency)

    def read_value(self):
        """Czytanie wartości z czujnika światła"""
        if not self.active:
            raise Exception(f"Czujnik {self.name} jest wyłączony.")

        current_hour = int(time.strftime("%H", time.localtime()))

        # Dostosowanie zakresu w zależności od godziny
        if 6 <= current_hour < 8:
            min_range, max_range = 300, 500
        elif 8 <= current_hour < 19:
            min_range, max_range = 800, 1000
        elif 19 <= current_hour < 22:
            min_range, max_range = 100, 300
        else:
            min_range, max_range = 0, 0

        if self.last_value is None:
            value = random.uniform(min_range, max_range)
        else:
            lower_bound = max(min_range, self.last_value - 10)
            upper_bound = min(max_range, self.last_value + 10)
            value = random.uniform(lower_bound, upper_bound)

        timestamp = datetime.now()
        self.last_value = value
        self._notify_callbacks(timestamp, value)  # Powiadomienie callbacków
        return value
