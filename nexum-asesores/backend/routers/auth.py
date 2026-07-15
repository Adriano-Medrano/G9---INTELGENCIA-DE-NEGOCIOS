# ============================================================
# routers/auth.py — JWT auth con aislamiento multi-tenant
# Cada token lleva claim cliente_id; los endpoints lo validan
# estrictamente → ninguna PYME puede ver datos de otra.
# ============================================================

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr
from datetime import datetime, timedelta, timezone
from typing import Optional
import jwt
import os
import logging

router = APIRouter()
logger = logging.getLogger("nexum.auth")
bearer = HTTPBearer()

# ── Config (en producción: variables de entorno / Vault) ──────
SECRET_KEY  = os.getenv("NEXUM_JWT_SECRET", "CHANGE_ME_IN_PRODUCTION_USE_VAULT")
ALGORITHM   = "HS256"
TOKEN_TTL_H = int(os.getenv("TOKEN_TTL_HOURS", "8"))


# ── Schemas ───────────────────────────────────────────────────
class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # segundos
    cliente_id: str
    cliente_nombre: str


class TokenData(BaseModel):
    cliente_id: str
    email: str
    exp: datetime


# ── Helpers ───────────────────────────────────────────────────
def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    to_encode["exp"] = datetime.now(timezone.utc) + timedelta(hours=TOKEN_TTL_H)
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> TokenData:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return TokenData(
            cliente_id=payload["cliente_id"],
            email=payload["email"],
            exp=datetime.fromtimestamp(payload["exp"], tz=timezone.utc),
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expirado. Inicia sesión de nuevo.",
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido.",
        )


# ── Dependency ────────────────────────────────────────────────
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
) -> TokenData:
    """
    Dependency que:
    1. Extrae el Bearer token del header Authorization.
    2. Valida la firma y expiración.
    3. Retorna el TokenData con cliente_id.

    Uso en otros routers:
        @router.get("/{cliente_id}")
        async def endpoint(
            cliente_id: str,
            user: TokenData = Depends(get_current_user)
        ):
            if user.cliente_id != cliente_id:
                raise HTTPException(403, "Acceso denegado")
    """
    return decode_token(credentials.credentials)


# ── Endpoints ─────────────────────────────────────────────────
import bcrypt
from db.connection import get_db_connection
from fastapi import Request
import asyncpg

@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db_connection),
):
    """
    Autentica a un usuario cliente del portal consultando PostgreSQL,
    verificando el hash bcrypt y registrando el acceso en audit_log.
    """
    query = """
        SELECT u.password_hash, u.cliente_id, u.nombre, c.razon_social
        FROM silver.stg_usuarios u
        LEFT JOIN silver.stg_clientes c ON u.cliente_id = c.cliente_id
        WHERE u.email = $1
    """
    user_row = await conn.fetchrow(query, body.email)

    if not user_row:
        logger.warning(f"Intento de login fallido: {body.email} (usuario no encontrado)")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales incorrectas.",
        )

    # Verificar contraseña con bcrypt
    pwd_bytes = body.password.encode('utf-8')
    hash_bytes = user_row['password_hash'].encode('utf-8')
    
    if not bcrypt.checkpw(pwd_bytes, hash_bytes):
        logger.warning(f"Intento de login fallido: {body.email} (contraseña incorrecta)")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales incorrectas.",
        )

    # Registrar en audit_log
    audit_query = """
        INSERT INTO silver.audit_log (cliente_id, usuario_email, endpoint, accion, ip_origen, user_agent)
        VALUES ($1, $2, $3, $4, $5, $6)
    """
    ip_origen = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")
    await conn.execute(
        audit_query,
        user_row['cliente_id'],
        body.email,
        "/auth/login",
        "login_exitoso",
        ip_origen,
        user_agent
    )

    token = create_access_token({
        "cliente_id": user_row["cliente_id"],
        "email":      body.email,
    })

    logger.info(f"Login exitoso: {body.email} → {user_row['cliente_id']}")

    return TokenResponse(
        access_token=token,
        expires_in=TOKEN_TTL_H * 3600,
        cliente_id=user_row["cliente_id"],
        cliente_nombre=user_row["razon_social"] or user_row["nombre"],
    )


@router.post("/refresh")
async def refresh_token(user: TokenData = Depends(get_current_user)):
    """Renueva el token si todavía es válido."""
    new_token = create_access_token({
        "cliente_id": user.cliente_id,
        "email":      user.email,
    })
    return {"access_token": new_token, "token_type": "bearer"}
