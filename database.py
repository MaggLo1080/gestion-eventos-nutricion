# database.py
import sqlite3

DB_FILE = "gestion_eventos.db"

def get_connection():
    """Genera una conexión a la base de datos con soporte de llaves foráneas activo."""
    conn = sqlite3.connect(DB_FILE)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    return conn

def inicializar_db():
    """Ejecuta los comandos DDL para estructurar las tablas adaptadas al Excel del cliente."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # 1. Tabla de Eventos
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS eventos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            fecha TEXT NOT NULL,
            descripcion TEXT
        );
    """)
    
    # 2. Tabla de Participantes (Actualizada con los campos de tu formulario/Excel)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS participantes (
            id TEXT PRIMARY KEY,                 -- Cédula de Ciudadanía
            nombre TEXT NOT NULL,                -- Nombre Completo
            correo_registro TEXT,                -- Endereço de e-mail
            correo TEXT,                         -- Correo electrónico de contacto
            whatsapp TEXT,                       -- WhatsApp / Teléfono
            profesion TEXT,                      -- Profesión
            marca_tiempo TEXT                    -- Carimbo de data/hora (Fecha de inscripción)
        );
    """)
    
    # 3. Tabla Pivot de Asistencias por Evento
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS asistencias (
            evento_id INTEGER,
            participante_id TEXT,
            asistio INTEGER DEFAULT 0 CHECK(asistio IN (0, 1)),
            hora_acreditacion TEXT,
            PRIMARY KEY (evento_id, participante_id),
            FOREIGN KEY (evento_id) REFERENCES eventos(id) ON DELETE CASCADE,
            FOREIGN KEY (participante_id) REFERENCES participantes(id) ON DELETE CASCADE
        );
    """)
    
    # Índices optimizados para búsquedas rápidas (por Cédula o Nombre completo)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_participante_nombre ON participantes(nombre);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_asistencia_evento ON asistencias(evento_id);")
    
    conn.commit()
    conn.close()
    print("📢 Base de datos e índices actualizados correctamente con los nuevos campos.")

if __name__ == "__main__":
    inicializar_db()