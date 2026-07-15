import os
import sqlite3
from typing import Optional, List
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, EmailStr

from database import get_connection

# ==========================================
# INICIALIZACIÓN AUTOMÁTICA DE LA BASE DE DATOS
# ==========================================
def inicializar_base_de_datos():
    """Crea las tablas necesarias en SQLite si aún no existen."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        # 1. Tabla de Eventos
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS eventos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                fecha TEXT NOT NULL,
                descripcion TEXT
            );
        """)
        
        # 2. Tabla de Participantes (con id como Cédula / TEXT)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS participantes (
                id TEXT PRIMARY KEY,
                nombre TEXT NOT NULL,
                correo_registro TEXT,
                correo TEXT,
                whatsapp TEXT,
                profesion TEXT,
                marca_tiempo TEXT
            );
        """)
        
        # 3. Tabla de Asistencias (control de acreditación por evento)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS asistencias (
                evento_id INTEGER,
                participante_id TEXT,
                asistio INTEGER DEFAULT 0,
                hora_acreditacion TEXT,
                PRIMARY KEY (evento_id, participante_id),
                FOREIGN KEY (evento_id) REFERENCES eventos (id),
                FOREIGN KEY (participante_id) REFERENCES participantes (id)
            );
        """)
        
        conn.commit()
        print("Base de datos verificada e inicializada correctamente.")
    except Exception as e:
        print(f"Error crítico al inicializar la base de datos: {e}")
        raise e
    finally:
        conn.close()

# Ejecutamos la verificación antes de que arranque la aplicación de FastAPI
inicializar_base_de_datos()


# 1. INICIALIZACIÓN DE LA APLICACIÓN
app = FastAPI(
    title="SGE - Centro de Nutrición Funcional",
    description="Sistema de Gestión de Eventos y Acreditación en Tiempo Real",
    version="1.0.0"
)

# 2. CONFIGURACIÓN DE CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 3. RUTA PRINCIPAL (Sirve la interfaz web)
@app.get("/", include_in_schema=False)
def index_web():
    """Sirve la interfaz gráfica en el navegador."""
    return FileResponse(os.path.join("templates", "index.html"))


# 4. MODELOS DE DATOS (Validaciones de entrada)
class EventoCrear(BaseModel):
    nombre: str
    fecha: str  # Formato YYYY-MM-DD
    descripcion: Optional[str] = None

class ParticipanteCrear(BaseModel):
    id: str  # Cédula
    nombre: str
    correo_registro: Optional[str] = None
    correo: Optional[EmailStr] = None
    whatsapp: Optional[str] = None
    profesion: Optional[str] = None
    marca_tiempo: Optional[str] = None


# 5. MÓDULO DE GESTIÓN DE EVENTOS
@app.post("/eventos", tags=["Eventos"])
def crear_evento(evento: EventoCrear):
    """Crea un nuevo evento en el sistema."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO eventos (nombre, fecha, descripcion)
            VALUES (?, ?, ?);
        """, (evento.nombre, evento.fecha, evento.descripcion))
        evento_id = cursor.lastrowid
        conn.commit()
        return {"status": "success", "message": "Evento creado exitosamente", "id": evento_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al crear evento: {e}")
    finally:
        conn.close()

@app.get("/eventos", tags=["Eventos"])
def listar_eventos():
    """Obtiene el historial de todos los eventos registrados."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM eventos ORDER BY fecha DESC;")
    eventos = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return eventos


# 6. MÓDULO DE ACREDITACIÓN Y BÚSQUEDA OPTIMIZADA
@app.get("/eventos/{evento_id}/buscar", tags=["Acreditación"])
def buscar_participantes_evento(evento_id: int, query: str = ""):
    """
    Busca participantes pre-registrados en un evento específico.
    Si el buscador está vacío, muestra una lista inicial de hasta 100 personas.
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    # Asegurar que el evento existe
    cursor.execute("SELECT id FROM eventos WHERE id = ?;", (evento_id,))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="El evento no existe.")

    # Búsqueda con el ajuste dinámico de volumen de datos
    if query.strip() == "":
        cursor.execute("""
            SELECT 
                p.id, p.nombre, p.correo, p.whatsapp, p.profesion,
                COALESCE(a.asistio, 0) as asistio,
                a.hora_acreditacion
            FROM participantes p
            LEFT JOIN asistencias a ON p.id = a.participante_id AND a.evento_id = ?
            ORDER BY p.nombre ASC
            LIMIT 100;
        """, (evento_id,))
    else:
        search_query = f"%{query}%"
        cursor.execute("""
            SELECT 
                p.id, p.nombre, p.correo, p.whatsapp, p.profesion,
                COALESCE(a.asistio, 0) as asistio,
                a.hora_acreditacion
            FROM participantes p
            LEFT JOIN asistencias a ON p.id = a.participante_id AND a.evento_id = ?
            WHERE p.id LIKE ? OR p.nombre LIKE ? OR p.correo LIKE ?
            ORDER BY p.nombre ASC;
        """, (evento_id, search_query, search_query, search_query))
    
    resultados = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return resultados

@app.post("/eventos/{evento_id}/acreditar/{participante_id}", tags=["Acreditación"])
def acreditar_participante(evento_id: int, participante_id: str):
    """Marca la asistencia en tiempo real de un participante."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT asistio FROM asistencias 
            WHERE evento_id = ? AND participante_id = ?;
        """, (evento_id, participante_id))
        row = cursor.fetchone()
        
        if row:
            cursor.execute("""
                UPDATE asistencias 
                SET asistio = 1, hora_acreditacion = datetime('now', 'localtime')
                WHERE evento_id = ? AND participante_id = ?;
            """, (evento_id, participante_id))
        else:
            cursor.execute("""
                INSERT INTO asistencias (evento_id, participante_id, asistio, hora_acreditacion)
                VALUES (?, ?, 1, datetime('now', 'localtime'));
            """, (evento_id, participante_id))
            
        conn.commit()
        return {"status": "success", "message": "Acreditación exitosa"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en la acreditación: {e}")
    finally:
        conn.close()


# 7. MÓDULO DE CREACIÓN/MODIFICACIÓN INDIVIDUAL DE PARTICIPANTES (DML)
@app.post("/participantes", tags=["Directorio Maestro"])
def crear_o_actualizar_participante(participante: ParticipanteCrear):
    """Inserta un nuevo participante en caliente o actualiza sus datos existentes."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO participantes (id, nombre, correo_registro, correo, whatsapp, profesion, marca_tiempo)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                nombre = excluded.nombre,
                correo = excluded.correo,
                whatsapp = excluded.whatsapp,
                profesion = excluded.profesion;
        """, (
            participante.id, participante.nombre, participante.correo_registro,
            str(participante.correo) if participante.correo else None,
            participante.whatsapp, participante.profesion, participante.marca_tiempo
        ))
        conn.commit()
        return {"status": "success", "message": "Participante guardado correctamente"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al guardar participante: {e}")
    finally:
        conn.close()
