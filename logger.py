import os
import json
import csv
import zipfile
import time
from datetime import datetime, timedelta
from typing import Dict, Iterator, Optional


class Logger:
    def __init__(self, config_path: str):
        """
        Inicjalizuje logger na podstawie pliku konfiguracyjnego.
        :param config_path: Ścieżka do pliku konfiguracyjnego (.json)
        """
        # Wczytanie konfiguracji z pliku JSON
        with open(config_path, 'r') as f:
            config = json.load(f)

        # Parametry z pliku konfiguracyjnego
        self.log_dir = config["log_dir"]
        self.filename_pattern = config["filename_pattern"]
        self.buffer_size = config["buffer_size"]
        self.rotate_every_hours = config["rotate_every_hours"]
        self.max_size_mb = config["max_size_mb"]
        self.rotate_after_lines = config["rotate_after_lines"]
        self.retention_days = config["retention_days"]

        # Inicjalizacja stanu loggera
        self.current_file = None
        self.current_file_path = None
        self.buffer = []
        self.line_count = 0
        self.last_rotation_time = datetime.now()

        # Tworzenie katalogów logów i archiwum
        os.makedirs(self.log_dir, exist_ok=True)
        os.makedirs(os.path.join(self.log_dir, "archive"), exist_ok=True)

    def start(self) -> None:
        """
        Otwiera nowy plik CSV do logowania. Jeśli plik jest nowy, zapisuje nagłówek.
        """
        filename = datetime.now().strftime(self.filename_pattern)
        self.current_file_path = os.path.join(self.log_dir, filename)

        file_exists = os.path.exists(self.current_file_path)
        # Open in 'a' mode for appending, 'newline=''' is crucial for csv.writer
        self.current_file = open(self.current_file_path, mode='a', newline='', encoding='utf-8')

        if not file_exists:
            writer = csv.writer(self.current_file, delimiter=';')
            writer.writerow(['timestamp', 'sensor_id', 'value', 'unit'])
            self.current_file.flush()  # Ensure header is written immediately

        self.line_count = 0
        self.last_rotation_time = datetime.now()

    def stop(self) -> None:
        """
        Wymusza zapis bufora i zamyka bieżący plik.
        """
        if self.current_file:
            self._flush_buffer()
            # No need to force check_rotation here, as flush_buffer is sufficient
            self.current_file.close()
            self.current_file = None

    def log_reading(self, sensor_id: str, timestamp: datetime, value: float, unit: str) -> None:
        """
        Dodaje wpis do bufora i ewentualnie wykonuje rotację pliku.
        """
        print(f"Logger callback: {sensor_id}, {timestamp}, {value}, {unit}")
        self.buffer.append([timestamp.strftime('%Y-%m-%d %H:%M:%S'), sensor_id, value, unit])

        if len(self.buffer) >= self.buffer_size:
            self._flush_buffer()

        self._check_rotation()

    def read_logs(self, start: datetime, end: datetime, sensor_id: Optional[str] = None) -> Iterator[Dict]:
        """
        Pobiera wpisy z logów w zadanym zakresie i (opcjonalnie) dla konkretnego czujnika.
        """
        log_files = self._get_log_files()

        for file_path in log_files:
            with open(file_path, 'r', newline='', encoding='utf-8') as file:
                reader = csv.DictReader(file, delimiter=';')
                for row in reader:
                    timestamp = datetime.strptime(row['timestamp'], "%Y-%m-%d %H:%M:%S")
                    if start <= timestamp <= end:
                        if sensor_id is None or row['sensor_id'] == sensor_id:
                            yield {
                                'timestamp': timestamp,
                                'sensor_id': row['sensor_id'],
                                'value': float(row['value']),
                                'unit': row['unit']
                            }

    def _flush_buffer(self) -> None:
        """
        Zapisuje bufor do pliku i czyści go.
        """
        if self.current_file and self.buffer:
            writer = csv.writer(self.current_file, delimiter=';')
            writer.writerows(self.buffer)
            self.line_count += len(self.buffer)
            self.buffer.clear()
            self.current_file.flush()  # Ensure data is written to disk
            # Optional: time.sleep(0.01) if you encounter very specific race conditions, but generally not needed

    def _check_rotation(self, force: bool = False) -> None:
        """
        Sprawdza, czy plik logu wymaga rotacji.
        """
        time_elapsed = (datetime.now() - self.last_rotation_time).total_seconds() / 3600

        # Check if the file exists before attempting to get its size
        file_size_mb = 0
        if os.path.exists(self.current_file_path):
            file_size_mb = os.path.getsize(self.current_file_path) / (1024 * 1024)

        if (force or
                self.line_count >= self.rotate_after_lines or
                file_size_mb >= self.max_size_mb or
                time_elapsed >= self.rotate_every_hours):
            self._rotate()

    def _rotate(self) -> None:
        """
        Wykonuje rotację - archiwizuje bieżący plik i otwiera nowy.
        """
        if self.current_file:
            self._flush_buffer()  # Ensure all buffered data is written before archiving
            self._archive_current_file()
            self.start()

    def _archive_current_file(self) -> None:
        """
        Archiwizuje aktualny plik logu do ZIP-a i usuwa oryginał.
        """
        archive_dir = os.path.join(self.log_dir, 'archive')
        # Generate archive name including a timestamp to ensure uniqueness if needed, or stick to original logic
        archive_name = os.path.basename(self.current_file_path).replace('.csv', '') + '_' + datetime.now().strftime(
            '%Y%m%d_%H%M%S') + ".zip"
        archive_path = os.path.join(archive_dir, archive_name)

        # Close the current file before archiving it
        if self.current_file:
            self.current_file.close()
            self.current_file = None

        if os.path.exists(self.current_file_path):
            with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                zipf.write(self.current_file_path, arcname=os.path.basename(self.current_file_path))

            # Add a small delay for OS to release file handle
            time.sleep(0.1)
            os.remove(self.current_file_path)

        self._clean_old_archives()

    def _clean_old_archives(self) -> None:
        """
        Usuwa archiwa starsze niż retention_days.
        """
        archive_dir = os.path.join(self.log_dir, 'archive')
        threshold_date = datetime.now() - timedelta(days=self.retention_days)

        for file_name in os.listdir(archive_dir):
            file_path = os.path.join(archive_dir, file_name)
            if os.path.isfile(file_path):
                # Use os.path.getctime for creation time or os.path.getmtime for modification time
                # Modification time is usually more appropriate for logs.
                file_mtime = datetime.fromtimestamp(os.path.getmtime(file_path))
                if file_mtime < threshold_date:
                    os.remove(file_path)

    def _get_log_files(self) -> list:
        """
        Zwraca listę ścieżek do plików logów (rozpakowuje archiwa, jeśli trzeba).
        """
        files = []
        # Aktywne pliki CSV w log_dir
        files.extend([os.path.join(self.log_dir, f) for f in os.listdir(self.log_dir) if f.endswith('.csv')])

        # Archiwalne pliki CSV z katalogu archive
        archive_dir = os.path.join(self.log_dir, 'archive')
        # Only iterate if archive_dir exists to prevent FileNotFoundError
        if os.path.exists(archive_dir):
            for zip_file_name in os.listdir(archive_dir):
                if zip_file_name.endswith('.zip'):
                    zip_file_path = os.path.join(archive_dir, zip_file_name)
                    try:
                        with zipfile.ZipFile(zip_file_path, 'r') as zipf:
                            # Extract to a temporary directory if you don't want to extract to archive_dir directly
                            # For simplicity, extracting to archive_dir for now.
                            zipf.extractall(archive_dir)
                            for name in zipf.namelist():
                                if name.endswith('.csv'):
                                    files.append(os.path.join(archive_dir, name))
                    except zipfile.BadZipFile:
                        print(f"Warning: Skipping corrupted zip file: {zip_file_path}")
        return files