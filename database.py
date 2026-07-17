import os
from supabase import create_client, Client

# 1. Leemos las credenciales HTTP desde las variables de entorno de Render.
# Mantenemos los valores por defecto en local por si deseas probar en tu máquina.
SUPABASE_URL = os.getenv(
    "SUPABASE_URL", 
    "https://ajtyzzanvjpcmmbwsfjx.supabase.co"
)
SUPABASE_KEY = os.getenv(
    "SUPABASE_KEY", 
    "sb_publishable_kgk5A_d37hTih02lNO-qaA_y9DRWxF3"
)

# 2. Inicializamos el cliente oficial de Supabase
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def get_supabase_client() -> Client:
    """Retorna el cliente HTTP para interactuar con el Centro de Nutrición Funcional."""
    return supabase
