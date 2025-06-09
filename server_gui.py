# server_gui.py
import tkinter as tk
from tkinter import ttk, messagebox
import os
import yaml
from datetime import datetime, timedelta
import threading
import time

# Importujemy zmieniony moduł serwera
# Upewnij się, że ścieżka do NetworkServer jest poprawna.
# Jeśli server.py jest w network/server.py, to:
from server.server import NetworkServer, SensorDataAggregator

class NetworkServerGUI:
    def __init__(self, master):
        self.master = master
        master.title("Network Server GUI")
        master.geometry("800x600") # Zwiększona geometria dla lepszej czytelności tabeli

        self.server = None
        self.server_thread = None
        # Agregator będzie przechowywany w instancji serwera, do której GUI będzie miało dostęp
        # self.aggregator = SensorDataAggregator() # Ta linia jest zbędna, bo GUI będzie używać self.server.aggregator

        # Ścieżka do plików konfiguracyjnych
        self.gui_config_path = "gui_config.yaml"
        self.main_config_path = "config.yaml" # Ścieżka do głównego pliku konfiguracyjnego
        self.load_gui_config() # Wczytuje początkowy port dla GUI

        self._create_widgets()
        self.update_gui_table() # Rozpocznij cykliczne aktualizowanie tabeli

    def load_gui_config(self):
        """Wczytuje konfigurację GUI (np. ostatnio używany port dla pola wpisu)."""
        if os.path.exists(self.gui_config_path):
            with open(self.gui_config_path, 'r') as f:
                config = yaml.safe_load(f)
                self.initial_port = config.get('port', 9999)
        else:
            self.initial_port = 9999 # Domyślny port, jeśli gui_config.yaml nie istnieje

    def save_gui_config(self):
        """Zapisuje konfigurację GUI (ostatnio używany port) do gui_config.yaml."""
        config = {'port': int(self.port_entry.get())}
        with open(self.gui_config_path, 'w') as f:
            yaml.dump(config, f)

    def _update_main_config_for_client(self, new_port: int):
        """
        Wczytuje config.yaml, aktualizuje port dla klienta
        i zapisuje zaktualizowany plik.
        """
        try:

            with open(self.main_config_path, 'r') as f:
                config = yaml.safe_load(f)

            if config is None: # Plik mógł być pusty
                config = {}
            if 'client' not in config:
                config['client'] = {}

            config['client']['port'] = new_port # Ustaw nowy port dla klienta

            with open(self.main_config_path, 'w') as f:
                yaml.dump(config, f, default_flow_style=False) # Zapisz z powrotem
            print(f"Zaktualizowano {self.main_config_path}: client.port ustawiony na {new_port}")
            # Możesz dodać logowanie do pliku lub do statusu GUI
        except FileNotFoundError:
            messagebox.showwarning("Błąd Konfiguracji", f"Plik {self.main_config_path} nie znaleziono. Nie można zaktualizować portu klienta.")
        except Exception as e:
            messagebox.showerror("Błąd Zapisu Konfiguracji", f"Nie udało się zaktualizować {self.main_config_path}: {e}")

    def _create_widgets(self):
        # Górny panel (Port, Start, Stop)
        top_frame = tk.Frame(self.master, pady=10)
        top_frame.pack(fill=tk.X)

        tk.Label(top_frame, text="Port Serwera:").pack(side=tk.LEFT, padx=5)
        self.port_entry = tk.Entry(top_frame, width=10)
        self.port_entry.insert(0, str(self.initial_port))
        self.port_entry.pack(side=tk.LEFT, padx=5)

        self.start_button = tk.Button(top_frame, text="Start Serwera", command=self.start_server_gui)
        self.start_button.pack(side=tk.LEFT, padx=5)

        self.stop_button = tk.Button(top_frame, text="Stop Serwera", command=self.stop_server_gui, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=5)

        # Środkowa część (Tabela czujników)
        self.tree = ttk.Treeview(self.master, columns=("Sensor", "Wartosc", "Jednostka", "Timestamp", "Sr1h", "Sr12h"), show="headings")
        self.tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.tree.heading("Sensor", text="Sensor")
        self.tree.heading("Wartosc", text="Wartość")
        self.tree.heading("Jednostka", text="Jednostka")
        self.tree.heading("Timestamp", text="Timestamp")
        self.tree.heading("Sr1h", text="Śr. 1h")
        self.tree.heading("Sr12h", text="Śr. 12h")

        self.tree.column("Sensor", width=80, anchor=tk.CENTER)
        self.tree.column("Wartosc", width=80, anchor=tk.CENTER)
        self.tree.column("Jednostka", width=80, anchor=tk.CENTER)
        self.tree.column("Timestamp", width=150, anchor=tk.CENTER)
        self.tree.column("Sr1h", width=80, anchor=tk.CENTER)
        self.tree.column("Sr12h", width=80, anchor=tk.CENTER)


        # Dolny panel (Pasek statusu)
        self.status_label = tk.Label(self.master, text="Status: Zatrzymany", bd=1, relief=tk.SUNKEN, anchor=tk.W)
        self.status_label.pack(side=tk.BOTTOM, fill=tk.X)

        # Powiąż zdarzenie zamknięcia okna
        self.master.protocol("WM_DELETE_WINDOW", self.on_closing)

    def on_closing(self):
        """Obsługa zamknięcia okna GUI."""
        if messagebox.askokcancel("Zamknij", "Czy na pewno chcesz zamknąć serwer?"):
            self.stop_server_gui() # Zatrzymuje serwer przed zamknięciem
            self.save_gui_config() # Zapisuje ostatnio używany port GUI
            self.master.destroy()

    def update_status(self, message):
        """Aktualizuje pasek statusu w GUI."""
        # Bezpieczna aktualizacja GUI z dowolnego wątku
        self.master.after(0, lambda: self.status_label.config(text=f"Status: {message}"))


    def on_new_sensor_data(self, sensor_id: str, timestamp: datetime, value: float, unit: str):
        """
        Callback wywoływany przez serwer, gdy nadejdą nowe dane.
        Ta funkcja jest wywoływana w wątku serwera.
        Nie aktualizujemy GUI bezpośrednio stąd, polegamy na cyklicznym odświeżaniu tabeli.
        """
        pass # Wszystko dzieje się w cyklicznej update_gui_table

    def start_server_gui(self):
        """Uruchamia serwer TCP w osobnym wątku."""
        try:
            port = int(self.port_entry.get())
            if not (1024 <= port <= 65535):
                raise ValueError("Port musi być liczbą całkowitą z zakresu 1024-65535.")

            self.server = NetworkServer(port)
            # Rejestrujemy callbacki do aktualizacji statusu i informacji o danych
            self.server.register_new_data_callback(self.on_new_sensor_data)
            self.server.register_status_callback(self.update_status)

            self.server_thread = threading.Thread(target=self.server.start, daemon=True)
            self.server_thread.start()

            self.start_button.config(state=tk.DISABLED)
            self.stop_button.config(state=tk.NORMAL)
            self.port_entry.config(state=tk.DISABLED) # Zablokuj edycję portu po starcie
            self.update_status(f"Próba uruchomienia serwera na porcie {port}...")

            # KLUCZOWA ZMIANA: Zapisz wybrany port do config.yaml dla klienta
            self._update_main_config_for_client(port)

        except ValueError as e:
            messagebox.showerror("Błąd Portu", str(e))
        except Exception as e:
            messagebox.showerror("Błąd Uruchamiania Serwera", f"Nie udało się uruchomić serwera: {e}")
            self.update_status(f"Błąd uruchamiania: {e}")
            self.stop_server_gui() # Resetuj przyciski, jeśli coś poszło nie tak

    def stop_server_gui(self):
        """Zatrzymuje serwer TCP."""
        if self.server:
            self.server.stop()
            self.server = None
            self.server_thread = None
            self.update_status("Zatrzymany")

        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        self.port_entry.config(state=tk.NORMAL) # Odblokuj edycję portu

    def update_gui_table(self):
        """
        Cyklicznie odświeża tabelę GUI na podstawie danych z agregatora serwera.
        Ta metoda jest wywoływana w głównym wątku Tkinter, co jest bezpieczne.
        """
        for item in self.tree.get_children():
            self.tree.delete(item) # Wyczyść stare dane

        if self.server and self.server.aggregator:
            sensor_ids = sorted(self.server.aggregator.get_all_sensor_ids())
            for s_id in sensor_ids:
                last_val_data = self.server.aggregator.get_last_value(s_id)
                if last_val_data:
                    last_value = last_val_data['value']
                    unit = last_val_data['unit']
                    timestamp = last_val_data['timestamp'].strftime('%Y-%m-%d %H:%M:%S')

                    avg_1h = self.server.aggregator.get_average(s_id, 1)
                    avg_12h = self.server.aggregator.get_average(s_id, 12)

                    self.tree.insert("", tk.END, values=(
                        s_id,
                        f"{last_value:.2f}",
                        unit,
                        timestamp,
                        f"{avg_1h:.2f}",
                        f"{avg_12h:.2f}"
                    ))

        self.master.after(2000, self.update_gui_table) # Odśwież co 2 sekundy

# Główna część programu
if __name__ == "__main__":
    root = tk.Tk()
    app = NetworkServerGUI(root)
    root.mainloop()