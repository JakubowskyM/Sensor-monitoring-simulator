import socket
import json
import time
import logging
from network.config import load_client_config


logger = logging.getLogger("NetworkClient")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
formatter = logging.Formatter('[%(levelname)s] %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

class NetworkClient:
    def __init__(self, host: str, port: int, timeout: float = 5.0, retries: int = 3):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.retries = retries
        self.sock = None
        logger.info(f"Klient sieciowy zainicjalizowany dla {host}:{port}. Oczekuje na jawne wywołanie .connect().")

    @classmethod
    def from_config(cls, path='config.yaml'):
        cfg = load_client_config(path)
        logger.info(f"Konfiguracja klienta wczytana z '{path}'.")
        return cls(cfg['host'], cfg['port'], cfg['timeout'], cfg['retries'])

    def connect(self):
        if self.sock:
            self.close()  # Jeśli jest już aktywne połączenie, zamknij je przed ponownym łączeniem
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        try:
            logger.info(f"Próba połączenia z {self.host}:{self.port}...")
            self.sock.connect((self.host, self.port))
            local_addr = self.sock.getsockname() # Pobierz lokalny port, aby potwierdzić połączenie
            logger.info(f"Połączono z {self.host}:{self.port} z lokalnego portu: {local_addr[1]}.")
        except Exception as e:
            logger.error(f"NIE UDAŁO SIĘ POŁĄCZYĆ z {self.host}:{self.port}: {e}")
            self.sock = None # Upewnij się, że gniazdo jest None, jeśli połączenie się nie powiodło
            raise # Ponownie zgłoś wyjątek, aby główna logika mogła to obsłużyć

    def close(self):
        if self.sock:
            try:
                self.sock.shutdown(socket.SHUT_RDWR)  # Zamknij gniazdo na obie strony
            except OSError as e:
                # Ignoruj błędy, jeśli połączenie już jest zerwane (np. przez serwer)
                logger.warning(f"Błąd podczas zamykania gniazda (shutdown): {e} (prawdopodobnie połączenie już zamknięte).")
            finally:
                self.sock.close()
                self.sock = None
                logger.info("Połączenie zamknięte.")
        else:
            logger.info("Brak aktywnego połączenia do zamknięcia.")

    def send(self, data: dict) -> bool:
        if not self.sock:
            logger.warning("Brak aktywnego połączenia podczas próby wysyłki. Próbuję nawiązać połączenie ponownie...")
            try:
                self.connect()
                logger.info("Ponowne połączenie nawiązane pomyślnie dla wysyłki.")
            except Exception as e:
                logger.error(f"Nie udało się ponownie połączyć, aby wysłać dane: {e}")
                return False

        message = self._serialize(data)
        attempts = 0

        while attempts < self.retries:
            try:
                self.sock.sendall(message + b"\n")
                response = self.sock.recv(1024)
                ack = self._deserialize(response.strip())

                if ack.get("status") == "ACK":
                    logger.info("Otrzymano potwierdzenie ACK od serwera.")
                    return True
                else:
                    logger.error(f"Brak ACK w odpowiedzi, status: {ack.get('status')}. Dane: {data}")
                    return False
            except (socket.error, json.JSONDecodeError) as e:
                logger.error(f"Błąd podczas wysyłania danych (próba {attempts + 1}/{self.retries}): {e}")
                # Spróbuj ponownie połączyć po błędzie sieciowym
                try:
                    self.connect()
                    logger.info("Pomyślnie nawiązano ponowne połączenie po błędzie wysyłki.")
                except Exception as ce:
                    logger.error(f"Błąd podczas próby ponownego łączenia po błędzie wysyłki: {ce}")
                    time.sleep(1) # Krótka pauza przed kolejną próbą
                attempts += 1

        logger.error(f"Nie udało się wysłać danych po maksymalnej liczbie prób ({self.retries}).")
        return False

    def _serialize(self, data: dict) -> bytes:
        return json.dumps(data).encode("utf-8")

    def _deserialize(self, raw: bytes) -> dict:
        return json.loads(raw.decode("utf-8"))
