import time
from datetime import datetime
import sys
import os # Potrzebne do dynamicznego określania ścieżek

# Zakładamy, że moduły sensors, logger i network są dostępne
from sensors import TemperatureSensor, HumiditySensor, PressureSensor, LightSensor
from logger import Logger
from network.client import NetworkClient
from network.config import load_client_config # Używamy oryginalnej nazwy load_client_config

# --- Zmienne globalne dla obsługi zamknięcia ---
# Pomaga to w dostępie do tych obiektów w bloku 'finally'
logger = None
client = None
sensors_list = []

def main():
    global logger, client, sensors_list

    base_dir = os.path.dirname(os.path.abspath(__file__))
    config_yaml_path = os.path.join(base_dir, "config.yaml")
    logger_config_path = os.path.join(base_dir, "Data", "config.json")

    # Wczytaj konfigurację sieci z YAML
    try:
        full_config = load_client_config(config_yaml_path)
        net_cfg = full_config.get("client", {})
    except FileNotFoundError as e:
        print(f"KRYTYCZNY BŁĄD: Nie znaleziono pliku konfiguracyjnego: {e}. Sprawdź ścieżkę: {config_yaml_path}.")
        sys.exit(1)
    except KeyError as e:
        print(f"KRYTYCZNY BŁĄD: Brak klucza w konfiguracji: {e} (sprawdź config.yaml).")
        sys.exit(1)
    except Exception as e:
        print(f"KRYTYCZNY BŁĄD podczas wczytywania konfiguracji sieci: {e}")
        sys.exit(1)

    # Zainicjuj klienta sieciowego
    client = NetworkClient(
        host=net_cfg.get("host", "127.0.0.1"),
        port=int(net_cfg.get("port", 9000)),
        timeout=float(net_cfg.get("timeout", 5.0)),
        retries=int(net_cfg.get("retries", 3)),
    )
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Klient sieciowy zainicjalizowany (oczekuje na jawne połączenie).")

    # Teraz połącz klienta sieciowego
    try:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Próba połączenia z serwerem pod adresem {net_cfg.get('host', '127.0.0.1')}:{net_cfg.get('port', 9000)}...")
        client.connect() # Jawnie wywołujemy metodę connect()
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Połączenie z serwerem nawiązane pomyślnie.")
    except Exception as e:
        print(f"KRYTYCZNY: Nie udało się połączyć z serwerem sieciowym: {e}. Zamykanie programu.")
        # Tutaj nie ma jeszcze loggera, więc nie logujemy przez niego
        sys.exit(1)

    #Zainicjuj loggera
    try:
        logger = Logger(config_path=logger_config_path, net_client=client)
        logger.start()
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Logger zainicjalizowany i uruchomiony.")
    except FileNotFoundError as e:
        print(f"KRYTYCZNY BŁĄD: Nie znaleziono pliku konfiguracyjnego loggera: {e}. Sprawdź ścieżkę: {logger_config_path}.")
        if client: client.close()
        sys.exit(1)
    except Exception as e:
        print(f"KRYTYCZNY BŁĄD podczas inicjalizacji loggera: {e}")
        if client: client.close()
        sys.exit(1)

    # Zainicjuj sensory
    tS = TemperatureSensor(sensor_id=1, name="TemperatureSensor", frequency=10)
    hS = HumiditySensor(sensor_id=2, name="HumiditySensor", frequency=10)
    pS = PressureSensor(sensor_id=3, name="PressureSensor", frequency=10)
    lS = LightSensor(sensor_id=4, name="LightSensor", frequency=10)

    sensors_list = [tS, hS, pS, lS]
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Sensory zainicjalizowane.")

    # Callback dla sensorów, który loguje i wysyła dane
    def sensor_data_handler(sensor_id, timestamp, value, unit):
        formatted_timestamp_str = timestamp.strftime('%Y-%m-%d %H:%M:%S')
        rounded_value = round(value, 2)

        # Logowanie do lokalnego loggera
        logger.log_reading(sensor_id, datetime.strptime(formatted_timestamp_str, '%Y-%m-%d %H:%M:%S'), rounded_value, unit)

        # Wyświetlanie na konsoli
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Odczyt: Sensor {sensor_id} ({unit}): {rounded_value:.2f}")

    # Rejestracja wspólnego callbacka dla wszystkich sensorów
    for s_obj in sensors_list:
        s_obj.register_callback(sensor_data_handler)

    #Główna pętla programu - aktywny odczyt i wysyłka danych z sensorów
    last_read_times = {sensor: 0 for sensor in sensors_list}

    try:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Rozpoczynam cykliczny odczyt i wysyłkę danych z sensorów. Naciśnij Ctrl+C, aby zakończyć.")
        while True:
            current_time = time.time()
            for sensor in sensors_list:
                if current_time - last_read_times[sensor] >= sensor.frequency:
                    sensor.read_value()
                    last_read_times[sensor] = current_time
            time.sleep(0.1)

    except KeyboardInterrupt:
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Program zakończony przez użytkownika (Ctrl+C).")
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] BŁĄD w głównej pętli programu: {e}")
        if logger:
            logger.log_reading("main_loop", datetime.now(), 0, f"main_loop_error: {type(e).__name__}")
    finally:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Rozpoczynam proces zamykania...")
        if client:
            client.close() # Zamknij klienta sieciowego
        if logger:
            logger.stop() # Zatrzymaj logger
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Czyszczenie zakończone. Program zakończył działanie.")

if __name__ == "__main__":
    main()