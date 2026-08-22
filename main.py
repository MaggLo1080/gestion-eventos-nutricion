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
from openpyxl import Workbook, load_workbook

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


# 3. CARGA INICIAL AUTOMÁTICA DE PARTICIPANTES (DESDE EXCEL O CSV)
def _extraer_registros_de_filas(filas_dict):
    """Recibe una lista de diccionarios (una fila = un dict de columna->valor)
    y devuelve el diccionario final {cedula: datos} listo para subir a Supabase.
    Comparte la misma lógica flexible de nombres de columna, sin importar si
    vino de un CSV o de un Excel.

    Si una fila no trae cédula/ID (por ejemplo, una base de prueba sin ese
    dato todavía), se le asigna un ID temporal autogenerado (PRUEBA-0001,
    PRUEBA-0002...) para que el sistema pueda diferenciar personas, incluso
    si comparten el mismo nombre. Estos IDs se reemplazan automáticamente
    apenas subas un archivo que sí incluya la columna de cédula real."""
    registros_dict = {}
    contador_sin_cedula = 0

    for row in filas_dict:
        cedula_raw = row.get("Cédula de Ciudadanía") or row.get("id") or row.get("cedula") or ""
        cedula_clean = str(cedula_raw).strip().split('.')[0]

        nombre = str(row.get("NOMBRES") or row.get("NOMBRE") or row.get("Nombre Completo") or row.get("nombre") or "").strip()

        if not cedula_clean or cedula_clean.lower() in ["nan", "none", "null", ""]:
            if not nombre:
                # Fila vacía o sin datos útiles: se descarta
                continue
            contador_sin_cedula += 1
            cedula_clean = f"PRUEBA-{contador_sin_cedula:04d}"

        correo_reg = str(row.get("Endereço de e-mail") or row.get("correo_registro") or "").strip()
        correo = str(row.get("Correo electrónico") or row.get("correo") or "").strip()
        whatsapp = str(row.get("WhatsApp") or row.get("whatsapp") or "").strip()
        profesion = str(row.get("Profesión") or row.get("profesion") or "").strip()
        estatus = str(row.get("ESTATUS") or row.get("Estatus") or row.get("estatus") or "").strip()
        marca_tiempo = str(row.get("Carimbo de data/hora") or row.get("marca_tiempo") or "").strip()

        registros_dict[cedula_clean] = {
            "id": cedula_clean,
            "nombre": nombre if nombre else "Sin Nombre",
            "correo_registro": correo_reg if correo_reg else None,
            "correo": correo if correo else None,
            "whatsapp": whatsapp if whatsapp else None,
            "profesion": profesion if profesion else None,
            "estatus": estatus if estatus else None,
            "marca_tiempo": marca_tiempo if marca_tiempo else None
        }

    return list(registros_dict.values())


def _leer_filas_desde_xlsx(archivo_path):
    """Lee un archivo .xlsx y devuelve una lista de diccionarios {columna: valor},
    usando la primera fila como encabezados."""
    wb = load_workbook(archivo_path, data_only=True)
    ws = wb.active

    filas = list(ws.iter_rows(values_only=True))
    if not filas:
        return []

    encabezados = [str(h).strip() if h is not None else "" for h in filas[0]]
    filas_dict = []
    for fila in filas[1:]:
        row_dict = {}
        for header, valor in zip(encabezados, fila):
            row_dict[header] = valor if valor is not None else ""
        filas_dict.append(row_dict)
    return filas_dict


def _leer_filas_desde_csv(archivo_path):
    """Lee un archivo .csv probando distintas codificaciones, devuelve lista de dicts."""
    for encoding in ["latin-1", "cp1252", "utf-8-sig", "utf-8"]:
        try:
            with open(archivo_path, mode="r", encoding=encoding) as f:
                reader = list(csv.DictReader(f))
                print(f"CSV leído exitosamente con codificación: {encoding}")
                return reader
        except (UnicodeDecodeError, Exception):
            continue
    return []


def cargar_excel_inicial():
    """Carga o actualiza los participantes desde participantes.xlsx (preferido)
    o participantes.csv (respaldo), soportando la columna ESTATUS."""
    try:
        ruta_xlsx = "participantes.xlsx"
        ruta_csv = "participantes.csv"

        filas_dict = []
        if os.path.exists(ruta_xlsx):
            print("Cargando participantes desde participantes.xlsx...")
            filas_dict = _leer_filas_desde_xlsx(ruta_xlsx)
        elif os.path.exists(ruta_csv):
            print("Cargando participantes desde participantes.csv...")
            filas_dict = _leer_filas_desde_csv(ruta_csv)
        else:
            print("No se encontró participantes.xlsx ni participantes.csv.")
            return

        registros = _extraer_registros_de_filas(filas_dict)

        if registros:
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
        print(f"❌ Error al cargar el archivo inicial de participantes: {e}")


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
    estatus: Optional[str] = None
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
        supabase.table("asistencias").delete().eq("evento_id", evento_id).execute()
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
        base_query = supabase.table("participantes").select("*")
        if query.strip():
            search_pattern = f"%{query.strip()}%"
            base_query = base_query.or_(
                f"id.ilike.{search_pattern},nombre.ilike.{search_pattern},correo.ilike.{search_pattern}"
            )

        participantes_res = base_query.order("nombre", desc=False).limit(1000).execute()
        participantes = participantes_res.data or []

        asistencias_res = supabase.table("asistencias")\
            .select("*")\
            .eq("evento_id", evento_id)\
            .limit(1000)\
            .execute()

        asistencias_map = {str(a["participante_id"]): a for a in (asistencias_res.data or [])}

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
                "estatus": p.get("estatus"),
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
        hora_colombia = (datetime.utcnow() - timedelta(hours=5)).strftime('%Y-%m-%d %H:%M:%S')

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
            "estatus": participante.estatus,
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
        supabase.table("asistencias").delete().eq("participante_id", participante_id).execute()
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


# 11. DESCARGAR REPORTE EXCEL DE ASISTENCIA
@app.get("/eventos/{evento_id}/excel", tags=["Acreditación y Asistencia"])
def descargar_reporte_excel(evento_id: str):
    """Genera y descarga un archivo Excel convirtiendo IDs correctamente."""
    try:
        try:
            id_evento_num = int(evento_id)
        except ValueError:
            id_evento_num = evento_id

        res_evento = supabase.table("eventos").select("nombre, fecha").eq("id", id_evento_num).execute()

        nombre_evento = "Evento"
        fecha_evento = "Reporte"
        if res_evento.data:
            nombre_evento = res_evento.data[0].get("nombre", "Evento")
            fecha_evento = res_evento.data[0].get("fecha", "Reporte")

        res_participantes = supabase.table("participantes").select("*").execute()
        participantes = res_participantes.data or []

        res_asistencias = supabase.table("asistencias")\
            .select("participante_id, hora_acreditacion, asistio")\
            .eq("evento_id", id_evento_num)\
            .execute()

        mapa_asistencia = {}
        for item in (res_asistencias.data or []):
            raw_p_id = str(item.get("participante_id") or "").strip().split('.')[0]
            if raw_p_id:
                hora_val = item.get("hora_acreditacion")
                mapa_asistencia[raw_p_id] = str(hora_val).strip() if hora_val else "Acreditado"

        wb = Workbook()
        ws = wb.active
        ws.title = "Reporte Asistencia"

        ws.append([
            "Cédula",
            "Nombre Completo",
            "Correo Electrónico",
            "WhatsApp",
            "Profesión",
            "Estatus",
            "Estado de Asistencia",
            "Hora de Acreditación"
        ])

        for p in participantes:
            raw_id = str(p.get("id") or "").strip().split('.')[0]

            asistio = raw_id in mapa_asistencia
            hora = mapa_asistencia.get(raw_id) if asistio else "-"

            ws.append([
                raw_id,
                p.get("nombre", ""),
                p.get("correo") or p.get("correo_registro") or "No registrado",
                p.get("whatsapp") or "No registrado",
                p.get("profesion") or "No definida",
                p.get("estatus") or "No definido",
                "PRESENTE" if asistio else "AUSENTE",
                hora
            ])

        output = io.BytesIO()
        wb.save(output)
        output.seek(0)

        nombre_limpio = "".join(c for c in nombre_evento if c.isalnum() or c in (' ', '_', '-')).strip()
        filename = f"Reporte_Asistencia_{nombre_limpio}_{fecha_evento}.xlsx"

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
