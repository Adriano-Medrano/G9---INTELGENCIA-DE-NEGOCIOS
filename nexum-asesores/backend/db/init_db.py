import os
import sys
import psycopg2
from pathlib import Path

def init_neon_db():
    print("Iniciando inicialización de la base de datos de Neon.tech...")
    
    # Obtener URL síncrona
    db_url = os.getenv("NEXUM_DB_SYNC_URL")
    if not db_url:
        print("ERROR: NEXUM_DB_SYNC_URL no está configurada en las variables de entorno.")
        sys.exit(1)
        
    try:
        # Conectar a Neon
        conn = psycopg2.connect(db_url)
        conn.autocommit = True
        cursor = conn.cursor()
        print("Conectado exitosamente a Neon.tech.")
        
        # Rutas de los archivos SQL
        db_dir = Path(__file__).parent
        silver_path = db_dir / "schema_silver.sql"
        gold_path = db_dir / "schema_gold.sql"
        
        # Ejecutar Silver
        if silver_path.exists():
            print("Ejecutando schema_silver.sql...")
            with open(silver_path, "r", encoding="utf-8") as f:
                sql_content = f.read().lstrip('\ufeff')
                cursor.execute(sql_content)
            print("Esquema SILVER creado con éxito.")
        else:
            print(f"ERROR: No se encontró schema_silver.sql en {silver_path}")
            
        # Ejecutar Gold
        if gold_path.exists():
            print("Ejecutando schema_gold.sql...")
            with open(gold_path, "r", encoding="utf-8") as f:
                sql_content = f.read().lstrip('\ufeff')
                cursor.execute(sql_content)
            print("Esquema GOLD creado con éxito.")
        else:
            print(f"ERROR: No se encontró schema_gold.sql en {gold_path}")
            
        cursor.close()
        conn.close()
        print("Base de datos de Neon.tech inicializada correctamente.")
        
    except Exception as e:
        print(f"ERROR DURANTE LA INICIALIZACIÓN: {e}")
        sys.exit(1)

if __name__ == "__main__":
    init_neon_db()
