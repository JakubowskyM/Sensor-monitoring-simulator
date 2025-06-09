import os
import json
import csv
import zipfile
import time
from datetime import datetime, timedelta
from typing import Dict, Iterator, Optional
from network.client import NetworkClient
import logging

class Logger:
    def __init__(self, config_path: str, net_client: Optional[NetworkClient] = None):
        # Wczytaj konfigurację
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)

        self.log_dir = config["log_dir"]
        self.filename_pattern = config["filename_pattern"]
        self.buffer_size = config["buffer_size"]
        self.rotate_every_hours = config["rotate_every_hours"]
        self.max_size_mb = config["max_size_mb"]
        self.rotate_after_lines = config["rotate_after_lines"]
        self.retention_days = config["retention_days"]

        self.current_file = None
        self.current_file_path = None
        self.buffer = []
        self.line_count = 0
        self.last_rotation_time = datetime.now()

        # Logger systemowy (stdout/debug)
        self.logger = logging.getLogger("LocalLogger")
        self.logger.setLevel(logging.INFO)
        if not self.logger.hasHandlers():
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
            self.logger.addHandler(handler)

        # Klient TCP (z config lub podany)
        self.net_client = net_client if net_client else NetworkClient.from_config()

        os.makedirs(self.log_dir, exist_ok=True)
        os.makedirs(os.path.join(self.log_dir, "archive"), exist_ok=True)

    def start(self) -> None:
        # Otwórz nowy plik logu zgodnie z wzorem nazwy
        filename = datetime.now().strftime(self.filename_pattern)
        self.current_file_path = os.path.join(self.log_dir, filename)

        file_exists = os.path.exists(self.current_file_path)
        self.current_file = open(self.current_file_path, mode='a', newline='', encoding='utf-8')

        if not file_exists:
            writer = csv.writer(self.current_file, delimiter=';')
            writer.writerow(['timestamp', 'sensor_id', 'value', 'unit'])
            self.current_file.flush()

        self.line_count = 0
        self.last_rotation_time = datetime.now()
        self.logger.info(f"Logger started with file: {self.current_file_path}")

    def stop(self) -> None:
        self._flush_buffer()
        if self.current_file:
            self.current_file.close()
            self.current_file = None
        self.logger.info("Logger stopped and file closed.")

    def log_reading(self, sensor_id: str, timestamp: datetime, value: float, unit: str) -> None:
        self.logger.info(f"Rejestracja: sensor_id={sensor_id}, timestamp={timestamp}, value={value}, unit={unit}")

        self.buffer.append([timestamp.strftime('%Y-%m-%d %H:%M:%S'), sensor_id, value, unit])

        self._send_to_server(sensor_id, timestamp, value, unit)

        if len(self.buffer) >= self.buffer_size:
            self._flush_buffer()

        self._check_rotation()

    def _send_to_server(self, sensor_id: str, timestamp: datetime, value: float, unit: str) -> None:
        payload = {
            "timestamp": timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            "sensor_id": sensor_id,
            "value": value,
            "unit": unit
        }

        try:
            success = self.net_client.send(payload)
            if success:
                self.logger.info("Wysłano dane na serwer (ACK).")
            else:
                self.logger.error("Błąd transmisji (brak ACK).")
        except Exception as e:
            self.logger.error(f"Wyjątek przy wysyłaniu do serwera: {e}")

    def read_logs(self, start: datetime, end: datetime, sensor_id: Optional[str] = None) -> Iterator[Dict]:
        files = self._get_log_files()

        for file_path in files:
            try:
                with open(file_path, 'r', newline='', encoding='utf-8') as file:
                    reader = csv.DictReader(file, delimiter=';')
                    for row in reader:
                        try:
                            ts = datetime.strptime(row['timestamp'], "%Y-%m-%d %H:%M:%S")
                            if start <= ts <= end and (sensor_id is None or row['sensor_id'] == sensor_id):
                                yield {
                                    'timestamp': ts,
                                    'sensor_id': row['sensor_id'],
                                    'value': float(row['value']),
                                    'unit': row['unit']
                                }
                        except Exception as e:
                            self.logger.warning(f"Błąd parsowania wiersza w {file_path}: {e}")
            except Exception as e:
                self.logger.warning(f"Nie udało się odczytać pliku {file_path}: {e}")

    def _flush_buffer(self) -> None:
        if not self.buffer or not self.current_file:
            return

        writer = csv.writer(self.current_file, delimiter=';')
        writer.writerows(self.buffer)
        self.line_count += len(self.buffer)
        self.buffer.clear()
        self.current_file.flush()
        self.logger.debug(f"Bufor wyczyszczony, zapisano {self.line_count} linii.")

    def _check_rotation(self, force: bool = False) -> None:
        time_elapsed_hours = (datetime.now() - self.last_rotation_time).total_seconds() / 3600
        file_size_mb = (os.path.getsize(self.current_file_path) / (1024 * 1024)) if os.path.exists(self.current_file_path) else 0

        if (force or
            self.line_count >= self.rotate_after_lines or
            file_size_mb >= self.max_size_mb or
            time_elapsed_hours >= self.rotate_every_hours):
            self.logger.info("Rotacja logu - warunki spełnione")
            self._rotate()

    def _rotate(self) -> None:
        self._flush_buffer()
        self._archive_current_file()
        self.start()

    def _archive_current_file(self) -> None:
        if self.current_file:
            self.current_file.close()
            self.current_file = None

        archive_dir = os.path.join(self.log_dir, 'archive')
        base_name = os.path.basename(self.current_file_path).replace('.csv', '')
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        archive_name = f"{base_name}_{timestamp}.zip"
        archive_path = os.path.join(archive_dir, archive_name)

        if os.path.exists(self.current_file_path):
            try:
                with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    zipf.write(self.current_file_path, arcname=os.path.basename(self.current_file_path))
                time.sleep(0.1)  # pewien odstęp dla pliku
                os.remove(self.current_file_path)
                self.logger.info(f"Zarchiwizowano plik logu do {archive_path}")
            except Exception as e:
                self.logger.error(f"Błąd archiwizacji pliku {self.current_file_path}: {e}")

        self._clean_old_archives()

    def _clean_old_archives(self) -> None:
        archive_dir = os.path.join(self.log_dir, 'archive')
        cutoff = datetime.now() - timedelta(days=self.retention_days)

        for file_name in os.listdir(archive_dir):
            file_path = os.path.join(archive_dir, file_name)
            if os.path.isfile(file_path):
                try:
                    mtime = datetime.fromtimestamp(os.path.getmtime(file_path))
                    if mtime < cutoff:
                        os.remove(file_path)
                        self.logger.info(f"Usunięto stary plik archiwum: {file_path}")
                except Exception as e:
                    self.logger.warning(f"Błąd usuwania pliku archiwum {file_path}: {e}")

    def _get_log_files(self) -> list:
        # Pobierz aktywne pliki CSV z katalogu logów
        files = [os.path.join(self.log_dir, f) for f in os.listdir(self.log_dir) if f.endswith('.csv')]

        archive_dir = os.path.join(self.log_dir, 'archive')
        if os.path.exists(archive_dir):
            for zip_name in os.listdir(archive_dir):
                if zip_name.endswith('.zip'):
                    zip_path = os.path.join(archive_dir, zip_name)
                    try:
                        with zipfile.ZipFile(zip_path, 'r') as zipf:
                            # Wyodrębnij tymczasowo pliki csv do katalogu archive
                            zipf.extractall(archive_dir)
                            for name in zipf.namelist():
                                if name.endswith('.csv'):
                                    files.append(os.path.join(archive_dir, name))
                    except zipfile.BadZipFile:
                        self.logger.warning(f"Pominięto uszkodzony plik zip: {zip_path}")
        return files
