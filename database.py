import sqlite3
import os

# Obtiene la ruta absoluta de la carpeta donde se encuentra este archivo
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "gestion_eventos.db")

def get_connection():
    """Establece una conexión con la base de datos SQLite asegurando permisos de escritura."""
    # El parámetro timeout ayuda si la base de datos está ocupada
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    return conn