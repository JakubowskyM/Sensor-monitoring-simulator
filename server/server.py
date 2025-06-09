# network/server.py
import os
import socket
import json
import logging
from threading import Thread, Event
import yaml
from collections import defaultdict, deque
from datetime import datetime, timedelta
import time

# Konfiguracja loggera dla serwera
logger = logging.getLogger("NetworkServer")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
formatter = logging.Formatter('[%(levelname)s] %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

# Klasa do przechowywania i agregacji danych sensorów
class SensorDataAggregator:
    def __init__(self):
        # Słownik przechowujący kolekcje (deques) odczytów dla każdego sensora
        # deque(maxlen=...) pozwala na automatyczne usuwanie najstarszych elementów
        self.sensor_data = defaultdict(lambda: deque(maxlen=10000)) # Przechowujemy do 10000 odczytów na sensor
        self.last_values = {} # Przechowuje ostatnią wartość dla każdego sensora

    def add_reading(self, sensor_id: str, timestamp: datetime, value: float, unit: str):
        self.sensor_data[sensor_id].append({'timestamp': timestamp, 'value': value, 'unit': unit})
        self.last_values[sensor_id] = {'value': value, 'unit': unit, 'timestamp': timestamp}

    def get_last_value(self, sensor_id: str):
        return self.last_values.get(sensor_id)

    def get_average(self, sensor_id: str, interval_hours: int) -> float:
        now = datetime.now()
        readings_in_interval = [
            d['value'] for d in self.sensor_data[sensor_id]
            if now - d['timestamp'] <= timedelta(hours=interval_hours)
        ]
        return sum(readings_in_interval) / len(readings_in_interval) if readings_in_interval else 0.0

    def get_all_sensor_ids(self):
        return list(self.last_values.keys())

class NetworkServer:
    def __init__(self, port: int):
        self.port = port
        self.server_socket = None
        self.client_threads = [] # Lista do przechowywania wątków klientów
        self.running_event = Event() # Sygnalizacja dla wątków, czy serwer działa
        self.new_data_callback = None # Callback do przekazywania nowych danych do GUI
        self.status_callback = None # Callback do informowania GUI o statusie serwera
        self.aggregator = SensorDataAggregator()

    @classmethod
    def from_config(cls, path='config.yaml'):
        base_path = os.path.dirname(os.path.dirname(__file__))
        abs_path = os.path.join(base_path, path)
        try:
            with open(abs_path, 'r') as file:
                config = yaml.safe_load(file)
            port = config['server']['port']
            logger.info(f"Port serwera wczytany z '{abs_path}': {port}")
            return cls(port)
        except FileNotFoundError:
            logger.error(f"Plik konfiguracyjny serwera nie znaleziony: {abs_path}. Używam domyślnego portu 9999.")
            return cls(9999) # Domyślny port
        except KeyError:
            logger.error(f"Brak klucza 'server.port' w pliku konfiguracyjnym: {abs_path}. Używam domyślnego portu 9999.")
            return cls(9999) # Domyślny port
        except Exception as e:
            logger.error(f"Błąd podczas wczytywania konfiguracji serwera: {e}. Używam domyślnego portu 9999.")
            return cls(9999) # Domyślny port

    def register_new_data_callback(self, callback):
        self.new_data_callback = callback

    def register_status_callback(self, callback):
        self.status_callback = callback

    def _set_status(self, status: str):
        if self.status_callback:
            self.status_callback(status)
        logger.info(f"Status serwera: {status}")

    def start(self):
        if self.server_socket:
            logger.warning("Serwer już działa. Zatrzymuję przed ponownym uruchomieniem.")
            self.stop()
            time.sleep(0.1) # Daj czas na zamknięcie poprzedniego gniazda

        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1) # Pozwala na natychmiastowe ponowne użycie adresu
            self.server_socket.bind(('', self.port))
            self.server_socket.listen(5) # Pozwala na 5 oczekujących połączeń
            self.running_event.set() # Ustaw flagę, że serwer działa
            self._set_status(f"Nasłuchiwanie na porcie {self.port}")
            logger.info(f"Serwer nasłuchuje na porcie {self.port}")

            # Uruchamiamy wątek akceptujący połączenia
            self.accept_thread = Thread(target=self._accept_connections, daemon=True)
            self.accept_thread.start()

        except Exception as e:
            self._set_status(f"Błąd uruchamiania: {e}")
            logger.error(f"Błąd uruchamiania serwera: {e}")
            self.server_socket = None

    def _accept_connections(self):
        while self.running_event.is_set():
            try:
                self.server_socket.settimeout(0.5) # Krótki timeout, aby sprawdzić running_event
                client_socket, addr = self.server_socket.accept()
                logger.info(f"Nowe połączenie od: {addr}")
                # Połączenie jest trwałe, aż klient się rozłączy lub serwer zostanie zatrzymany
                client_thread = Thread(target=self._handle_client, args=(client_socket, addr), daemon=True)
                self.client_threads.append(client_thread)
                client_thread.start()
            except socket.timeout:
                continue # Sprawdzaj dalej running_event
            except OSError as e:
                if self.running_event.is_set(): # Tylko jeśli serwer miał być uruchomiony
                    logger.error(f"Błąd akceptacji połączenia (prawdopodobnie gniazdo zamknięte): {e}")
                break # Wyjdź z pętli, jeśli gniazdo zostało zamknięte z zewnątrz
            except Exception as e:
                logger.error(f"Nieoczekiwany błąd podczas akceptacji połączeń: {e}")
                if not self.running_event.is_set(): # Jeśli serwer jest zatrzymywany, to może być normalne
                    break


    def _handle_client(self, client_socket, addr):
        with client_socket:
            buffer = b""
            try:
                while self.running_event.is_set(): # Kontynuuj obsługę, dopóki serwer działa
                    data = client_socket.recv(1024)
                    if not data:
                        logger.info(f"Klient {addr} rozłączył się")
                        break # Wyjdź z pętli, klient się rozłączył
                    buffer += data

                    while b"\n" in buffer:
                        line, buffer = buffer.split(b"\n", 1)
                        try:
                            message = json.loads(line.decode("utf-8"))
                            logger.info(f"Odebrano dane od {addr}: {message}")

                            # Dodaj odczyt do agregatora
                            sensor_id = message.get("sensor_id")
                            timestamp_str = message.get("timestamp")
                            value = message.get("value")
                            unit = message.get("unit")

                            if all([sensor_id, timestamp_str, value is not None, unit]):
                                try:
                                    # Parsowanie timestampu do obiektu datetime
                                    timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
                                    self.aggregator.add_reading(sensor_id, timestamp, float(value), unit)

                                    # Wywołaj callback, aby powiadomić GUI o nowych danych
                                    if self.new_data_callback:
                                        self.new_data_callback(sensor_id, timestamp, float(value), unit)
                                except ValueError as ve:
                                    logger.error(f"Błąd parsowania danych sensora: {ve} dla wiadomości: {message}")
                            else:
                                logger.warning(f"Odebrano niekompletne dane sensora: {message}")


                            ack = json.dumps({"status": "ACK"}) + "\n"
                            client_socket.sendall(ack.encode("utf-8"))
                        except json.JSONDecodeError:
                            logger.error(f"Nieprawidłowy format JSON od {addr}: {line.decode('utf-8', errors='ignore')}")
                            # Możesz wysłać NACK lub po prostu zignorować
                        except Exception as e:
                            logger.error(f"Błąd wewnętrzny podczas obsługi wiadomości od {addr}: {e}")

            except socket.error as e:
                logger.warning(f"Błąd połączenia z klientem {addr}: {e}")
            except Exception as e:
                logger.error(f"Nieoczekiwany błąd obsługi klienta {addr}: {e}")

    def stop(self):
        self.running_event.clear() # Sygnalizuj wątkom, aby się zatrzymały
        self._set_status("Zatrzymywanie...")
        logger.info("Zatrzymywanie serwera...")

        # Zamknij server_socket, aby odblokować accept()
        if self.server_socket:
            try:
                self.server_socket.shutdown(socket.SHUT_RDWR)
                self.server_socket.close()
            except OSError as e:
                logger.warning(f"Błąd podczas zamykania gniazda serwera (shutdown): {e}")
            finally:
                self.server_socket = None

        # Poczekaj na zakończenie wątków klientów (z krótkim timeoutem)
        for t in self.client_threads:
            if t.is_alive():
                logger.debug(f"Czekam na zakończenie wątku klienta {t.name}...")
                t.join(timeout=1.0) # Poczekaj max 1 sekundę
        self.client_threads = [] # Wyczyść listę wątków

        if self.accept_thread and self.accept_thread.is_alive():
            logger.debug("Czekam na zakończenie wątku akceptującego...")
            self.accept_thread.join(timeout=1.0) # Poczekaj na zakończenie wątku akceptującego

        self._set_status("Zatrzymany")
        logger.info("Serwer zatrzymany.")

# Ten blok nie będzie uruchamiany, gdy serwer jest importowany do GUI
# Ale zostawiam go dla testów samodzielnych
if __name__ == "__main__":
    # Testowy przykład użycia ServerDataAggregator
    agg = SensorDataAggregator()
    agg.add_reading("temp1", datetime.now() - timedelta(minutes=5), 25.0, "C")
    agg.add_reading("temp1", datetime.now() - timedelta(minutes=10), 24.0, "C")
    agg.add_reading("temp1", datetime.now() - timedelta(hours=2), 20.0, "C")
    agg.add_reading("hum1", datetime.now() - timedelta(minutes=5), 60.0, "%RH")

    print(f"Ostatnia wartość temp1: {agg.get_last_value('temp1')}")
    print(f"Średnia temp1 (1h): {agg.get_average('temp1', 1)}")
    print(f"Średnia temp1 (12h): {agg.get_average('temp1', 12)}")
    print(f"Średnia hum1 (1h): {agg.get_average('hum1', 1)}")

    # Uruchomienie serwera bez GUI do testów
    server = NetworkServer.from_config() # Spróbuje wczytać z config.yaml, inaczej domyślny 9999
    # Symuluj callback dla GUI (w normalnym użyciu, to GUI by go dostarczało)
    def dummy_data_callback(sensor_id, timestamp, value, unit):
        print(f"[CALLBACK] Nowe dane dla {sensor_id}: {value} {unit} @ {timestamp}")
    def dummy_status_callback(status):
        print(f"[STATUS] {status}")

    server.register_new_data_callback(dummy_data_callback)
    server.register_status_callback(dummy_status_callback)

    server.start()
    try:
        while True:
            time.sleep(1)
            # Możesz tutaj co jakiś czas wyświetlać dane z agregatora
            # print("---- Stan agregatora ----")
            # for s_id in server.aggregator.get_all_sensor_ids():
            #    print(f"{s_id}: Ostatnia: {server.aggregator.get_last_value(s_id)}, Średnia 1h: {server.aggregator.get_average(s_id, 1):.2f}")
    except KeyboardInterrupt:
        server.stop()