# mi_api_proyecto

API RESTful construida con **FastAPI**, generada como conducto principal para exponer el Modelo Económico y el Modelo Predictivo del proyecto RENIEC (Grupo 9), permitiendo al equipo de Dashboard comenzar la integración sin bloqueos.

## 📁 Estructura del proyecto

```
mi_api_proyecto/
├── main.py                # Código principal de la API
├── requirements.txt       # Dependencias (fastapi, uvicorn)
├── README.md              # Este archivo
└── .gitignore             # Ignorar entornos virtuales (venv) y caché
```

## 🚀 Instrucciones para ejecutar el proyecto

### 1. Crear un entorno virtual (recomendado)

```bash
python3 -m venv venv
source venv/bin/activate     # En Windows: venv\Scripts\activate
```

### 2. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 3. Ejecutar el servidor

```bash
uvicorn main:app --reload
```

La API quedará disponible en: `http://127.0.0.1:8000`

### 4. Documentación interactiva automática

FastAPI genera documentación automáticamente:

- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`

## 📡 Endpoints disponibles

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/` | Health check — verifica que la API está funcionando |
| GET | `/api/modelo-economico` | Devuelve datos simulados del Modelo Económico (Axl) |
| POST | `/api/prediccion` | Devuelve una predicción de ventas simulada (Modelo Predictivo, Axel) |

### Ejemplos de respuesta

**GET /**
```json
{"mensaje": "¡La API está funcionando!"}
```

**GET /api/modelo-economico**
```json
{
  "status": "success",
  "data": {
    "pbi_proyectado": 3.5,
    "inflacion_estimada": 2.1,
    "tendencia": "positiva"
  }
}
```

**POST /api/prediccion**
```json
{
  "status": "success",
  "prediccion_ventas": 15420.50,
  "nivel_confianza": 0.95
}
```

## 👥 Autores

Grupo 9 — Facultad de Ingeniería de Sistemas e Informática, UNMSM
