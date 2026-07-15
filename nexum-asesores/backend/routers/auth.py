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
@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest):
    """
    Autentica a un usuario cliente del portal.

    En producción:
    - Consulta PostgreSQL: SELECT * FROM usuarios WHERE email = :email
    - Verifica contraseña con bcrypt
    - Registra intento en audit_log

    Aquí: mock con datos de prueba.
    """
    # TODO: reemplazar con consulta real a PostgreSQL
    MOCK_USERS = {
        "demo@pyme.es": {
            "password_hash": "nexum2026",  # usar bcrypt en prod
            "cliente_id":    "CL-2024-0042",
            "nombre":        "Tecnopyme SL",
        },
    }

    user = MOCK_USERS.get(body.email)
    if not user or user["password_hash"] != body.password:
        logger.warning(f"Intento de login fallido: {body.email}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales incorrectas.",
        )

    token = create_access_token({
        "cliente_id": user["cliente_id"],
        "email":      body.email,
    })

    logger.info(f"Login exitoso: {body.email} → {user['cliente_id']}")

    return TokenResponse(
        access_token=token,
        expires_in=TOKEN_TTL_H * 3600,
        cliente_id=user["cliente_id"],
        cliente_nombre=user["nombre"],
    )


@router.post("/refresh")
async def refresh_token(user: TokenData = Depends(get_current_user)):
    """Renueva el token si todavía es válido."""
    new_token = create_access_token({
        "cliente_id": user.cliente_id,
        "email":      user.email,
    })
    return {"access_token": new_token, "token_type": "bearer"}
