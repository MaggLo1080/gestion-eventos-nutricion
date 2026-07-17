import os
import psycopg2
from psycopg2.extras import RealDictCursor

# 1. Intentamos leer la URL de conexión desde las variables de entorno de Render.
# Si no existe (por ejemplo, si estás corriendo el proyecto en local), usa la de Supabase.
DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    "postgresql://postgres:ZeqrsB2HiqYoqnpg@db.ajtyzzanvjpcmmbwsfjx.supabase.co:5432/postgres"
)

def get_connection():
    """Establece una conexión con la base de datos PostgreSQL en Supabase."""
    # Conectamos usando la URL definitiva
    conn = psycopg2.connect(DATABASE_URL)
    
    # RealDictCursor hace exactamente lo mismo que sqlite3.Row: 
    # Permite acceder a las columnas por su nombre (ej: fila['nombre']) en lugar de por índice.
    conn.cursor_factory = RealDictCursor
    
    return conn
