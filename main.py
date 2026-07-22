import os
import csv
import io
from typing import Optional, List
from fastapi import FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, EmailStr
from datetime import datetime, timedelta

# Generación ligera de Excel
from openpyxl import Workbook

# Importamos el cliente HTTP unificado
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
    """Carga o actualiza los participantes del CSV soportando la codificación de tu archivo."""
    try:
        archivo_path = "participantes.csv"
        
        if not os.path.exists(archivo_path):
            print("No se encontró el archivo participantes.csv.")
            return

        contenido = None
        # Probamos distintos encodings compatibles con tu archivo
        for encoding in ["latin-1", "cp1252", "utf-8-sig", "utf-8"]:
            try:
                with open(archivo_path, mode="r", encoding=encoding) as f:
                    reader = list(csv.DictReader(f))
                    contenido = reader
                    print(f"CSV leído exitosamente con codificación: {encoding}")
                    break
            except (UnicodeDecodeError, Exception):
                continue

        if contenido:
            registros_dict = {}  # Usamos un diccionario para eliminar duplicados por Cédula antes de enviar a Supabase

            for row in contenido:
                # Extraer cédula de forma flexible
                cedula_raw = row.get("Cédula de Ciudadanía") or row.get("id") or row.get("cedula") or ""
                cedula_clean = str(cedula_raw).strip().split('.')[0]  # Limpiar espacios y decimales

                # Ignorar filas sin cédula válida
                if not cedula_clean or cedula_clean.lower() in ["nan", "none", "null", ""]:
                    continue

                nombre = str(row.get("Nombre Completo") or row.get("nombre") or "").strip()
                correo_reg = str(row.get("Endereço de e-mail") or row.get("correo_registro") or "").strip()
                correo = str(row.get("Correo electrónico") or row.get("correo") or "").strip()
                whatsapp = str(row.get("WhatsApp") or row.get("whatsapp") or "").strip()
                profesion = str(row.get("Profesión") or row.get("profesion") or "").strip()
                marca_tiempo = str(row.get("Carimbo de data/hora") or row.get("marca_tiempo") or "").strip()

                # Guardamos en el diccionario (los registros posteriores actualizarán los anteriores si la cédula se repite)
                registros_dict[cedula_clean] = {
                    "id": cedula_clean,
                    "nombre": nombre if nombre else "Sin Nombre",
                    "correo_registro": correo_reg if correo_reg else None,
                    "correo": correo if correo else None,
                    "whatsapp": whatsapp if whatsapp else None,
                    "profesion": profesion if profesion else None,
                    "marca_tiempo": marca_tiempo if marca_tiempo else None
                }

            registros = list(registros_dict.values())

            if registros:
                # Insertar/Actualizar en lotes de 50 para evitar límites de payload
                tamano_lote = 50
                total_cargados = 0
                
                for i in range(0, len(registros), tamano_lote):
                    lote = registros[i:i + tamano_lote]
                    supabase.table("participantes").upsert(lote).execute()
                    total_cargados += len(lote)
                
                print(f"✅ Cargados/Actualizados {total_cargados} participantes válidos en Supabase (en lotes).")
            else:
                print("⚠️ No se encontraron registros válidos para cargar.")

    except Exception as e:
        print(f"❌ Error al cargar CSV inicial: {e}")


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

@app.delete("/eventos/{evento_id}", tags=["Eventos"])
def eliminar_evento(evento_id: int):
    """Elimina un evento y todas sus asistencias registradas."""
    try:
        # 1. Elimina asistencias asociadas al evento
        supabase.table("asistencias").delete().eq("evento_id", evento_id).execute()
        
        # 2. Elimina el evento
        supabase.table("eventos").delete().eq("id", evento_id).execute()
        
        return {"mensaje": f"Evento {evento_id} eliminado exitosamente."}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al eliminar el evento: {str(e)}"
        )


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
        
        participantes_res = base_query.order("nombre", desc=False).limit(1000).execute()
        participantes = participantes_res.data or []

        # 2. Obtener las asistencias para este evento específico
        asistencias_res = supabase.table("asistencias")\
            .select("*")\
            .eq("evento_id", evento_id)\
            .limit(1000)\
            .execute()
        
        # Crear un mapa rápido {participante_id: registro_asistencia}
        asistencias_map = {str(a["participante_id"]): a for a in (asistencias_res.data or [])}

        # 3. Combinar datos
        resultados = []
        for p in participantes:
            id_str = str(p["id"])
            asistencia = asistencias_map.get(id_str)
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


# 9. MÓDULO DE ELIMINACIÓN DE PARTICIPANTES
@app.delete("/participantes/{participante_id}", tags=["Directorio Maestro"])
def eliminar_participante(participante_id: str):
    """Elimina un participante del directorio y todas sus asistencias asociadas."""
    try:
        # 1. Elimina asistencias asociadas al participante
        supabase.table("asistencias").delete().eq("participante_id", participante_id).execute()
        
        # 2. Elimina al participante
        supabase.table("participantes").delete().eq("id", participante_id).execute()
        
        return {"status": "success", "message": f"Participante {participante_id} eliminado exitosamente."}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al eliminar participante: {str(e)}"
        )


# 10. DESMARCAR ASISTENCIA A UN EVENTO
@app.delete("/eventos/{evento_id}/acreditar/{participante_id}", tags=["Acreditación y Asistencia"])
def desmarcar_asistencia(evento_id: str, participante_id: str):
    """Elimina el registro de asistencia de un participante en un evento especifico."""
    try:
        supabase.table("asistencias")\
            .delete()\
            .eq("evento_id", evento_id)\
            .eq("participante_id", participante_id)\
            .execute()
            
        return {"status": "success", "message": "Asistencia desmarcada correctamente."}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al desmarcar asistencia: {str(e)}"
        )


# 11. DESCARGAR REPORTE EXCEL DE ASISTENCIA (CORREGIDO)
@app.get("/eventos/{evento_id}/excel", tags=["Acreditación y Asistencia"])
def descargar_reporte_excel(evento_id: str):
    """Genera y descarga un archivo Excel convirtiendo IDs correctamente."""
    try:
        # Convertir evento_id a entero para consultas en BD
        try:
            id_evento_num = int(evento_id)
        except ValueError:
            id_evento_num = evento_id

        # 1. Obtener los datos del evento
        res_evento = supabase.table("eventos").select("nombre, fecha").eq("id", id_evento_num).execute()
        
        nombre_evento = "Evento"
        fecha_evento = "Reporte"
        if res_evento.data:
            nombre_evento = res_evento.data[0].get("nombre", "Evento")
            fecha_evento = res_evento.data[0].get("fecha", "Reporte")

        # 2. Obtener todos los participantes registrados
        res_participantes = supabase.table("participantes").select("*").execute()
        participantes = res_participantes.data or []

        # 3. Obtener asistencias registradas para este evento
        res_asistencias = supabase.table("asistencias")\
            .select("participante_id, hora_acreditacion, asistio")\
            .eq("evento_id", id_evento_num)\
            .execute()
        
        # Mapa de asistencias normalizando la cédula/ID a string sin decimales ni espacios
        mapa_asistencia = {}
        for item in (res_asistencias.data or []):
            raw_p_id = str(item.get("participante_id") or "").strip().split('.')[0]
            if raw_p_id:
                hora_val = item.get("hora_acreditacion")
                # Si asistio == 1 o tiene valor, guardamos la hora
                mapa_asistencia[raw_p_id] = str(hora_val).strip() if hora_val else "Acreditado"

        # 4. Crear el libro Excel con OpenPyXL
        wb = Workbook()
        ws = wb.active
        ws.title = "Reporte Asistencia"

        # Encabezados
        ws.append([
            "Cédula", 
            "Nombre Completo", 
            "Correo Electrónico", 
            "WhatsApp", 
            "Profesión", 
            "Estado de Asistencia", 
            "Hora de Acreditación"
        ])

        # Agregar filas
        for p in participantes:
            # Normalizar cédula del participante
            raw_id = str(p.get("id") or "").strip().split('.')[0]
            
            asistio = raw_id in mapa_asistencia
            hora = mapa_asistencia.get(raw_id) if asistio else "-"

            ws.append([
                raw_id,
                p.get("nombre", ""),
                p.get("correo") or p.get("correo_registro") or "No registrado",
                p.get("whatsapp") or "No registrado",
                p.get("profesion") or "No definida",
                "PRESENTE" if asistio else "AUSENTE",
                hora
            ])

        # 5. Guardar en buffer de memoria
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)

        # Sanear el nombre del archivo
        nombre_limpio = "".join(c for c in nombre_evento if c.isalnum() or c in (' ', '_', '-')).strip()
        filename = f"Reporte_Asistencia_{nombre_limpio}_{fecha_evento}.xlsx"

        # 6. Retornar respuesta
        headers = {
            'Content-Disposition': f'attachment; filename="{filename}"',
            'Access-Control-Expose-Headers': 'Content-Disposition'
        }
        return StreamingResponse(
            output, 
            headers=headers, 
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error al generar el archivo Excel: {str(e)}"
        )
