import os
import csv
from typing import Optional, List
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, EmailStr
from datetime import datetime, timedelta

# Importamos el cliente HTTP unificado que configuramos previamente
from database import get_supabase_client

# Inicializamos el cliente oficial de Supabase
supabase = get_supabase_client()

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


# 3. CARGA INICIAL AUTOMÁTICA DE PARTICIPANTES (DESDE ARCHIVO CSV)
def cargar_excel_inicial():
    """Carga los participantes del archivo CSV a Supabase si la tabla está vacía."""
    try:
        # Verificar si la tabla de participantes ya tiene datos
        check = supabase.table("participantes").select("id", count="exact").limit(1).execute()
        if check.count and check.count > 0:
            print("La base de datos de participantes ya contiene registros.")
            return

        # Busca el archivo CSV en el directorio raíz del proyecto
        archivo_path = "participantes.csv"  # Asegúrate de que tu archivo se llame así en el repositorio
        
        if os.path.exists(archivo_path):
            with open(archivo_path, mode="r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                registros = []
                for row in reader:
                    registros.append({
                        "id": str(row.get("id") or row.get("cedula") or row.get("documento") or "").strip(),
                        "nombre": str(row.get("nombre", "")).strip(),
                        "correo_registro": str(row.get("correo_registro", "")).strip(),
                        "correo": str(row.get("correo", "")).strip(),
                        "whatsapp": str(row.get("whatsapp", "")).strip(),
                        "profesion": str(row.get("profesion", "")).strip(),
                        "marca_tiempo": str(row.get("marca_tiempo", "")).strip()
                    })
                
                # Insertar en lotes a Supabase
                if registros:
                    supabase.table("participantes").upsert(registros).execute()
                    print(f"Cargados {len(registros)} participantes exitosamente desde el archivo CSV.")
    except Exception as e:
        print(f"Aviso al cargar CSV inicial: {e}")

# Ejecutamos la carga al iniciar la API
cargar_excel_inicial()


# 4. RUTA PRINCIPAL (Sirve la interfaz web)
@app.get("/", include_in_schema=False)
def index_web():
    """Sirve la interfaz gráfica en el navegador."""
    return FileResponse(os.path.join("templates", "index.html"))


# 5. MODELOS DE DATOS (Validaciones de entrada)
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


# 6. MÓDULO DE GESTIÓN DE EVENTOS
@app.post("/eventos", tags=["Eventos"])
def crear_evento(evento: EventoCrear):
    """Crea un nuevo evento en el sistema."""
    try:
        data = {
            "nombre": evento.nombre,
            "fecha": evento.fecha,
            "descripcion": evento.descripcion
        }
        response = supabase.table("eventos").insert(data).execute()
        
        if not response.data:
            raise HTTPException(status_code=500, detail="No se pudo recuperar el ID del evento creado.")
            
        evento_id = response.data[0]['id']
        return {"status": "success", "message": "Evento creado exitosamente", "id": evento_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al crear evento: {e}")

@app.get("/eventos", tags=["Eventos"])
def listar_eventos():
    """Obtiene el historial de todos los eventos registrados."""
    try:
        response = supabase.table("eventos").select("*").order("fecha", desc=True).execute()
        return response.data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al listar eventos: {e}")


# 7. MÓDULO DE ACREDITACIÓN Y BÚSQUEDA OPTIMIZADA
@app.get("/eventos/{evento_id}/buscar", tags=["Acreditación"])
def buscar_participantes_evento(evento_id: int, query: str = ""):
    """Busca participantes y mapea su estado de asistencia para un evento específico."""
    try:
        # 1. Obtener participantes
        base_query = supabase.table("participantes").select("*")
        if query.strip():
            search_pattern = f"%{query.strip()}%"
            base_query = base_query.or_(
                f"id.ilike.{search_pattern},nombre.ilike.{search_pattern},correo.ilike.{search_pattern}"
            )
        
        participantes_res = base_query.order("nombre", desc=False).limit(100).execute()
        participantes = participantes_res.data or []

        # 2. Obtener las asistencias para este evento específico
        asistencias_res = supabase.table("asistencias")\
            .select("*")\
            .eq("evento_id", evento_id)\
            .execute()
        
        # Crear un mapa rápido {participante_id: registro_asistencia}
        asistencias_map = {a["participante_id"]: a for a in (asistencias_res.data or [])}

        # 3. Combinar datos
        resultados = []
        for p in participantes:
            asistencia = asistencias_map.get(p["id"])
            resultados.append({
                "id": p["id"],
                "nombre": p["nombre"],
                "correo": p.get("correo") or p.get("correo_registro"),
                "whatsapp": p.get("whatsapp"),
                "profesion": p.get("profesion"),
                "asistio": asistencia["asistio"] if asistencia else 0,
                "hora_acreditacion": asistencia["hora_acreditacion"] if asistencia else None
            })
            
        return resultados
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en la búsqueda de participantes: {e}")


@app.post("/eventos/{evento_id}/acreditar/{participante_id}", tags=["Acreditación"])
def acreditar_participante(evento_id: int, participante_id: str):
    """Marca la asistencia en tiempo real de un participante."""
    try:
        # Hora local de Colombia (UTC-5)
        hora_colombia = (datetime.utcnow() - timedelta(hours=5)).strftime('%Y-%m-%d %H:%M:%S')

        # Usar upsert para insertar o actualizar en un solo paso
        payload = {
            "evento_id": evento_id,
            "participante_id": participante_id,
            "asistio": 1,
            "hora_acreditacion": hora_colombia
        }
        
        supabase.table("asistencias").upsert(payload).execute()
            
        return {"status": "success", "message": "Acreditación exitosa", "hora_acreditacion": hora_colombia}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en la acreditación: {e}")


# 8. MÓDULO DE CREACIÓN/MODIFICACIÓN INDIVIDUAL DE PARTICIPANTES (DML)
@app.post("/participantes", tags=["Directorio Maestro"])
def crear_o_actualizar_participante(participante: ParticipanteCrear):
    """Inserta un nuevo participante en caliente o actualiza sus datos existentes."""
    try:
        data = {
            "id": participante.id,
            "nombre": participante.nombre,
            "correo_registro": participante.correo_registro,
            "correo": str(participante.correo) if participante.correo else None,
            "whatsapp": participante.whatsapp,
            "profesion": participante.profesion,
            "marca_tiempo": participante.marca_tiempo
        }
        
        supabase.table("participantes").upsert(data).execute()
        return {"status": "success", "message": "Participante guardado correctamente"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al guardar participante: {e}")
