# importador.py
import pandas as pd
import sqlite3
from database import get_connection, inicializar_db

def importar_excel_a_db(file_path: str):
    """
    Lee un archivo de Excel con los campos del formulario del evento 
    y los importa a la tabla de participantes de forma segura.
    """
    print(f"📖 Cargando el archivo: {file_path}...")
    
    try:
        # 1. Leer el Excel usando pandas
        # Nota: Asegúrate de que las columnas coincidan exactamente con tu archivo
        df = pd.read_excel(file_path)
        
        # Mapeo de columnas basado en la imagen (Excel -> SQL)
        # Cambia los nombres de la izquierda si cambian en tu Excel real.
        column_mapping = {
            'Cédula de Ciudadanía': 'id',
            'Nombre Completo': 'nombre',
            'Endereço de e-mail': 'correo_registro',
            'Correo electrónico': 'correo',
            'WhatsApp': 'whatsapp',
            'Profesión': 'profesion',
            'Carimbo de data/hora': 'marca_tiempo'
        }
        
        # Renombrar columnas para facilitar el manejo
        df = df.rename(columns=column_mapping)
        
        # Mantener únicamente las columnas requeridas por nuestra base de datos
        columnas_validas = list(column_mapping.values())
        df = df[[col for col in columnas_validas if col in df.columns]]
        
        # 2. Limpieza básica de datos
        # SQLite no tolera nulos en las llaves primarias, limpiamos y convertimos a texto
        df = df.dropna(subset=['id', 'nombre'])
        df['id'] = df['id'].astype(str).str.strip()
        df['nombre'] = df['nombre'].astype(str).str.strip()
        
        # Reemplazar valores NaN restantes por cadenas vacías para evitar errores de tipo en SQL
        df = df.fillna('')
        
        # 3. Insertar datos en la Base de Datos SQLite
        conn = get_connection()
        cursor = conn.cursor()
        
        registros_insertados = 0
        
        for _, row in df.iterrows():
            # Usamos "INSERT OR REPLACE" para actualizar los datos si la Cédula (id) ya existe
            cursor.execute("""
                INSERT OR REPLACE INTO participantes (id, nombre, correo_registro, correo, whatsapp, profesion, marca_tiempo)
                VALUES (?, ?, ?, ?, ?, ?, ?);
            """, (
                row['id'],
                row['nombre'],
                row['correo_registro'],
                row['correo'],
                row['whatsapp'],
                row['profesion'],
                row['marca_tiempo']
            ))
            registros_insertados += 1
            
        conn.commit()
        conn.close()
        
        print(f"✅ ¡Éxito! Se procesaron e importaron {registros_insertados} participantes en la base de datos.")
        
    except FileNotFoundError:
        print(f"❌ Error: El archivo '{file_path}' no fue encontrado. Verifica la ruta.")
    except Exception as e:
        print(f"❌ Ocurrió un error inesperado durante la importación: {e}")

if __name__ == "__main__":
    # Nos aseguramos de que las tablas existan antes de la importación
    inicializar_db()
    
    # Nombre de tu archivo Excel de prueba en la misma carpeta
    archivo_prueba = "registro_formulario.xlsx" 
    importar_excel_a_db(archivo_prueba)