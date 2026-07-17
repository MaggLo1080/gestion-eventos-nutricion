import os
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
    try:
        data = {
            "nombre": evento.nombre,
            "fecha": evento.fecha,
            "descripcion": evento.descripcion
        }
        # Insertamos y solicitamos que devuelva la fila creada para capturar el ID
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


# 6. MÓDULO DE ACREDITACIÓN Y BÚSQUEDA OPTIMIZADA
@app.get("/eventos/{evento_id}/buscar", tags=["Acreditación"])
def buscar_participantes_evento(evento_id: int, query: str = ""):
    """
    Busca participantes pre-registrados en un evento específico.
    Si el buscador está vacío, muestra una lista inicial de hasta 100 personas.
    """
    try:
        # Asegurar que el evento existe
        evento_check = supabase.table("eventos").select("id").eq("id", evento_id).execute()
        if not evento_check.data:
            raise HTTPException(status_code=404, detail="El evento no existe.")

        # Construimos la consulta base al directorio de participantes incluyendo la relación de asistencia
        # El Join se realiza de forma automática mediante la API PostgREST de Supabase
        base_query = supabase.table("participantes").select(
            "id, nombre, correo, whatsapp, profesion, asistencias(asistio, hora_acreditacion)"
        )

        if query.strip() == "":
            response = base_query.order("nombre", desc=False).limit(100).execute()
        else:
            search_pattern = f"%{query}%"
            # Filtro usando lógica OR para ID, nombre o correo (equivalente a ILIKE en SQL)
            response = base_query.or_(
                f"id.ilike.{search_pattern},nombre.ilike.{search_pattern},correo.ilike.{search_pattern}"
            ).order("nombre", desc=False).execute()
        
        # Formateamos la respuesta para que la estructura JSON sea idéntica a la que espera el Frontend
        resultados = []
        for p in response.data:
            # Buscamos si el participante tiene una asistencia registrada para ESTE evento específico
            asistencia_evento = [a for a in p.get("asistencias", []) if a.get("evento_id") == evento_id]
            
            asistio = 0
            hora_acreditacion = None
            if asistencia_evento:
                asistio = asistencia_evento[0].get("asistio", 0)
                hora_acreditacion = asistencia_evento[0].get("hora_acreditacion")

            resultados.append({
                "id": p["id"],
                "nombre": p["nombre"],
                "correo": p["correo"],
                "whatsapp": p["whatsapp"],
                "profesion": p["profesion"],
                "asistio": asistio,
                "hora_acreditacion": hora_acreditacion
            })
            
        return resultados
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en la búsqueda de participantes: {e}")

@app.post("/eventos/{evento_id}/acreditar/{participante_id}", tags=["Acreditación"])
def acreditar_participante(evento_id: int, participante_id: str):
    """Marca la asistencia en tiempo real de un participante."""
    try:
        # Calculamos la hora local de Colombia (UTC-5) usando Python
        hora_colombia = (datetime.utcnow() - timedelta(hours=5)).strftime('%Y-%m-%d %H:%M:%S')

        # Verificamos si ya existe un registro de asistencia previo
        check = supabase.table("asistencias").select("asistio")\
            .eq("evento_id", evento_id)\
            .eq("participante_id", participante_id).execute()
        
        if check.data:
            # Si existe, actualizamos el estado
            supabase.table("asistencias").update({
                "asistio": 1,
                "hora_acreditacion": hora_colombia
            }).eq("evento_id", evento_id).eq("participante_id", participante_id).execute()
        else:
            # Si no existe, creamos el registro de asistencia en caliente
            supabase.table("asistencias").insert({
                "evento_id": evento_id,
                "participante_id": participante_id,
                "asistio": 1,
                "hora_acreditacion": hora_colombia
            }).execute()
            
        return {"status": "success", "message": "Acreditación exitosa"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en la acreditación: {e}")


# 7. MÓDULO DE CREACIÓN/MODIFICACIÓN INDIVIDUAL DE PARTICIPANTES (DML)
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
        
        # En el SDK oficial de Supabase, "upsert" resuelve de forma nativa el ON CONFLICT (id)
        supabase.table("participantes").upsert(data).execute()
        return {"status": "success", "message": "Participante guardado correctamente"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al guardar participante: {e}")
