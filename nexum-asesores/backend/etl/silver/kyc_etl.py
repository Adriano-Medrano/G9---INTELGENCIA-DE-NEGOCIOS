import logging
import os
import sys

# Ensure backend root is in PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from db.connection import get_sync_pool

logger = logging.getLogger("nexum.etl.kyc")

def run_kyc_transform():
    """
    Ejecuta el cruce de datos financieros con el padrón RENIEC.
    Actualiza la capa Silver (stg_facturas) con las verificaciones de identidad.
    """
    logger.info("Iniciando transformación KYC (Cruce Facturas <-> RENIEC)")
    pool = get_sync_pool()
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            # 1. Marcar facturas con contrapartes fallecidas
            cur.execute("""
                UPDATE silver.stg_facturas f
                SET contraparte_fallecida = TRUE
                FROM silver.stg_reniec_padron p
                WHERE f.proveedor_cliente = p.dni AND p.estado_vida = 'fallecido';
            """)
            logger.info(f"Marcadas {cur.rowcount} facturas con contrapartes fallecidas.")
            
            # 2. Marcar facturas con identidades válidas
            cur.execute("""
                UPDATE silver.stg_facturas f
                SET identidad_verificada = TRUE
                FROM silver.stg_reniec_padron p
                WHERE f.proveedor_cliente = p.dni AND p.estado_vida = 'vivo';
            """)
            logger.info(f"Verificadas {cur.rowcount} identidades cruzadas exitosamente.")
            
            # 3. Marcar facturas donde la identidad no se encontró en RENIEC
            cur.execute("""
                UPDATE silver.stg_facturas f
                SET identidad_verificada = FALSE
                WHERE f.proveedor_cliente IS NOT NULL 
                  AND NOT EXISTS (
                      SELECT 1 FROM silver.stg_reniec_padron p 
                      WHERE p.dni = f.proveedor_cliente
                  );
            """)
            logger.info(f"Marcadas {cur.rowcount} facturas con DNIs no encontrados en padrón.")

            conn.commit()
            logger.info("Transformación KYC finalizada exitosamente.")
    except Exception as e:
        conn.rollback()
        logger.error(f"Error en transformación KYC: {e}")
        raise
    finally:
        pool.putconn(conn)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_kyc_transform()
