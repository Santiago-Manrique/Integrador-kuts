"""
=============================================================
  COWORKING SPACE — Authentication Backend
  Módulo: auth.py
  Patrones: Observer, Factory Method
  + JWT + bcrypt + Supabase
=============================================================
"""

from __future__ import annotations
from abc import abstractmethod

import bcrypt
import jwt
import re
import uuid
import json
from datetime import datetime, timedelta
from typing import Any

from supabase import create_client, Client

# ---------- JWT Secret (cambiar en producción) ----------
JWT_SECRET = "nexo_coworking_super_secret_key_2025"
JWT_EXPIRATION_HOURS = 2

# ---------- Supabase ----------
SUPABASE_URL = "https://kyjszgpgyykktbhsqqjg.supabase.co"
SUPABASE_KEY = "sb_publishable_7XJYNkkzzbg7HZC7bEqv3w_zxFFxd8U"   

# Inicializamos el cliente UNA sola vez para todo el módulo (Mejora drástica de rendimiento)
supabase_client: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


# ═══════════════════════════════════════════════════════════════
# SECCIÓN 1 ─ OBSERVER PATTERN
# ═══════════════════════════════════════════════════════════════

class AuthEvent:
    USER_REGISTERED  = "USER_REGISTERED"
    LOGIN_SUCCESS    = "LOGIN_SUCCESS"
    LOGIN_FAILED     = "LOGIN_FAILED"
    ACCOUNT_LOCKED   = "ACCOUNT_LOCKED"
    PASSWORD_CHANGED = "PASSWORD_CHANGED"

    def __init__(self, event_type: str, payload: dict[str, Any]):
        self.event_type = event_type
        self.payload    = payload
        self.timestamp  = datetime.utcnow().isoformat()

    def __repr__(self) -> str:
        return f"AuthEvent(type={self.event_type}, at={self.timestamp})"


class AuthObserver:
    def update(self, event: AuthEvent) -> None:
        ...


class AuthEventBus:
    def __init__(self):
        self._observers: list[AuthObserver] = []

    def subscribe(self, observer: AuthObserver) -> None:
        if observer not in self._observers:
            self._observers.append(observer)

    def unsubscribe(self, observer: AuthObserver) -> None:
        self._observers = [o for o in self._observers if o is not observer]

    def publish(self, event: AuthEvent) -> None:
        for observer in self._observers:
            observer.update(event)


class ConsoleLogger(AuthObserver):
    def update(self, event: AuthEvent) -> None:
        print(f"[LOG] {event.timestamp} | {event.event_type} | {event.payload}")


class DatabaseObserver(AuthObserver):
    """Persiste cada evento de autenticación en la tabla auth_events de Supabase."""
    def __init__(self, db_path: str = None):
        pass # Acepta un arg opcional por compatibilidad con código viejo

    def update(self, event: AuthEvent) -> None:
        try:
            supabase_client.table("auth_events").insert({
                "event_type": event.event_type,
                "payload":    json.dumps(event.payload),
                "timestamp":  event.timestamp,
            }).execute()
        except Exception as exc:
            print(f"[DatabaseObserver] Error al guardar evento: {exc}")


class EmailNotifier(AuthObserver):
    def update(self, event: AuthEvent) -> None:
        if event.event_type == AuthEvent.USER_REGISTERED:
            # ── INTEGRAR EMAIL ──
            pass


# ═══════════════════════════════════════════════════════════════
# SECCIÓN 2 ─ MODELOS DE USUARIO
# ═══════════════════════════════════════════════════════════════

class User:
    def __init__(
        self,
        user_id:       str,
        username:      str,
        email:         str,
        password_hash: str,
        role:          str,
    ):
        self.user_id       = user_id
        self.username      = username
        self.email         = email
        self.password_hash = password_hash
        self.role          = role
        self.is_active     = True
        self.created_at    = datetime.utcnow().isoformat()
        self.failed_attempts: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id":    self.user_id,
            "username":   self.username,
            "email":      self.email,
            "role":       self.role,
            "is_active":  self.is_active,
            "created_at": self.created_at,
        }


class MemberUser(User):
    def __init__(self, user_id, username, email, password_hash):
        super().__init__(user_id, username, email, password_hash, role="member")


class AdminUser(User):
    def __init__(self, user_id, username, email, password_hash):
        super().__init__(user_id, username, email, password_hash, role="admin")


class GuestUser(User):
    def __init__(self, user_id, username, email, password_hash):
        super().__init__(user_id, username, email, password_hash, role="guest")


# ═══════════════════════════════════════════════════════════════
# SECCIÓN 3 ─ FACTORY METHOD
# ═══════════════════════════════════════════════════════════════

class UserFactory:
    @abstractmethod
    def create_user(self, user_id, username, email, password_hash) -> User:
        ...

    def build(self, username, email, password_hash) -> User:
        user_id = str(uuid.uuid4())
        return self.create_user(user_id, username, email, password_hash)


class MemberFactory(UserFactory):
    def create_user(self, user_id, username, email, password_hash) -> MemberUser:
        return MemberUser(user_id, username, email, password_hash)


class AdminFactory(UserFactory):
    def create_user(self, user_id, username, email, password_hash) -> AdminUser:
        return AdminUser(user_id, username, email, password_hash)


class GuestFactory(UserFactory):
    def create_user(self, user_id, username, email, password_hash) -> GuestUser:
        return GuestUser(user_id, username, email, password_hash)


class UserFactoryRegistry:
    _factories: dict[str, UserFactory] = {
        "member": MemberFactory(),
        "admin":  AdminFactory(),
        "guest":  GuestFactory(),
    }

    @classmethod
    def get(cls, role: str) -> UserFactory:
        factory = cls._factories.get(role.lower())
        if not factory:
            raise ValueError(f"Rol desconocido: '{role}'. Disponibles: {list(cls._factories)}")
        return factory

    @classmethod
    def register(cls, role: str, factory: UserFactory) -> None:
        cls._factories[role.lower()] = factory


# ═══════════════════════════════════════════════════════════════
# SECCIÓN 4 ─ REPOSITORIO
# ═══════════════════════════════════════════════════════════════

class UserRepository:
    def save(self, user: User) -> None: ...
    def find_by_username(self, username: str) -> User | None: ...
    def find_by_email(self, email: str) -> User | None: ...
    def update(self, user: User) -> None: ...


class InMemoryUserRepository(UserRepository):
    """Repositorio en memoria (útil para tests)."""

    def __init__(self):
        self._store: dict[str, User] = {}

    def save(self, user: User) -> None:
        self._store[user.username] = user

    def find_by_username(self, username: str) -> User | None:
        return self._store.get(username)

    def find_by_email(self, email: str) -> User | None:
        return next((u for u in self._store.values() if u.email == email), None)

    def update(self, user: User) -> None:
        if user.username in self._store:
            self._store[user.username] = user


class SupabaseUserRepository(UserRepository):
    """Repositorio persistente usando Supabase."""
    def __init__(self, db_path: str = None):
        pass # Acepta db_path para no romper compatibilidad con api.py

    def _row_to_user(self, row: dict) -> User:
        role = row.get("role", "member")
        constructors = {
            "member": MemberUser,
            "admin":  AdminUser,
            "guest":  GuestUser,
        }
        cls = constructors.get(role, MemberUser)
        user = cls(
            user_id       = row["user_id"],
            username      = row["username"],
            email         = row["email"],
            password_hash = row["password_hash"],
        )
        user.is_active       = bool(row.get("is_active", True))
        user.failed_attempts = row.get("failed_attempts", 0)
        user.created_at      = row.get("created_at", datetime.utcnow().isoformat())
        return user

    def save(self, user: User) -> None:
        supabase_client.table("users").insert({
            "user_id":         user.user_id,
            "username":        user.username,
            "email":           user.email,
            "password_hash":   user.password_hash,
            "role":            user.role,
            "is_active":       int(user.is_active), # ← ¡Acá está la magia! Forzamos 1 o 0
            "failed_attempts": user.failed_attempts,
            "created_at":      user.created_at,
        }).execute()

    def find_by_username(self, username: str) -> User | None:
        response = supabase_client.table("users").select("*").eq("username", username).execute()
        if response.data:
            return self._row_to_user(response.data[0])
        return None

    def find_by_email(self, email: str) -> User | None:
        response = supabase_client.table("users").select("*").eq("email", email).execute()
        if response.data:
            return self._row_to_user(response.data[0])
        return None
    
    def get_all(self) -> list[User]:
        """Obtiene todos los usuarios registrados en Supabase."""
        response = supabase_client.table("users").select("*").execute()
        if response.data:
            return [self._row_to_user(row) for row in response.data]
        return []
    
    def update(self, user: User) -> None:
        supabase_client.table("users").update({
            "email":           user.email,
            "password_hash":   user.password_hash,
            "is_active":       int(user.is_active), # ← Acá también
            "failed_attempts": user.failed_attempts,
        }).eq("username", user.username).execute()


# Alias clave para mantener compatibilidad con el servidor Flask actual
SQLiteUserRepository = SupabaseUserRepository


# ═══════════════════════════════════════════════════════════════
# SECCIÓN 5 ─ VALIDACIONES Y HASHING
# ═══════════════════════════════════════════════════════════════

class PasswordPolicy:
    MIN_LENGTH = 8

    @classmethod
    def validate(cls, password: str) -> tuple[bool, list[str]]:
        errors = []
        if len(password) < cls.MIN_LENGTH:
            errors.append(f"Debe tener al menos {cls.MIN_LENGTH} caracteres.")
        if not re.search(r"[A-Z]", password):
            errors.append("Debe contener al menos una letra mayúscula.")
        if not re.search(r"[a-z]", password):
            errors.append("Debe contener al menos una letra minúscula.")
        if not re.search(r"\d", password):
            errors.append("Debe contener al menos un número.")
        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
            errors.append("Debe contener al menos un carácter especial.")
        return (len(errors) == 0, errors)


class InputValidator:
    @staticmethod
    def is_valid_username(username: str) -> tuple[bool, str]:
        if not username or len(username) < 3:
            return False, "El nombre de usuario debe tener al menos 3 caracteres."
        if len(username) > 30:
            return False, "El nombre de usuario no puede superar los 30 caracteres."
        if not re.match(r"^[a-zA-Z0-9_]+$", username):
            return False, "El nombre de usuario solo puede contener letras, números y guiones bajos."
        return True, ""

    @staticmethod
    def is_valid_email(email: str) -> tuple[bool, str]:
        pattern = r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$"
        if not re.match(pattern, email):
            return False, "El correo electrónico no tiene un formato válido."
        return True, ""
        
    @staticmethod
    def passwords_match(password: str, confirm: str) -> tuple[bool, str]:
        if password != confirm:
            return False, "Las contraseñas no coinciden."
        return True, ""


class PasswordHasher:
    """Clase restaurada para aislar la lógica de encriptación y no romper los tests."""
    @staticmethod
    def hash(plain_password: str) -> str:
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(plain_password.encode('utf-8'), salt).decode('utf-8')

    @staticmethod
    def verify(plain_password: str, hashed: str) -> bool:
        return bcrypt.checkpw(plain_password.encode('utf-8'), hashed.encode('utf-8'))


# ═══════════════════════════════════════════════════════════════
# SECCIÓN 6 ─ RESULTADO DE AUTENTICACIÓN
# ═══════════════════════════════════════════════════════════════

class AuthResult:
    def __init__(self, success: bool, message: str, data: dict | None = None, errors: list | None = None):
        self.success = success
        self.message = message
        self.data    = data or {}
        self.errors  = errors or []

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "message": self.message,
            "data":    self.data,
            "errors":  self.errors,
        }


# ═══════════════════════════════════════════════════════════════
# SECCIÓN 7 ─ SERVICIO DE AUTENTICACIÓN
# ═══════════════════════════════════════════════════════════════

MAX_FAILED_ATTEMPTS = 5

class AuthService:
    def __init__(self, repository: UserRepository, event_bus: AuthEventBus):
        self._repo      = repository
        self._event_bus = event_bus

    def _generate_token(self, user: User) -> str:
        payload = {
            "user_id":  user.user_id,
            "username": user.username,
            "role":     user.role,
            "exp":      datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS),
        }
        return jwt.encode(payload, JWT_SECRET, algorithm="HS256")

    def sign_up(self, username: str, email: str, password: str, confirm_password: str, role: str = "member") -> AuthResult:
        errors = []

        ok, msg = InputValidator.is_valid_username(username)
        if not ok:
            errors.append(msg)

        ok, msg = InputValidator.is_valid_email(email)
        if not ok:
            errors.append(msg)
            
        ok, msg = InputValidator.passwords_match(password, confirm_password)
        if not ok:
            errors.append(msg)

        ok, pwd_errors = PasswordPolicy.validate(password)
        if not ok:
            errors.extend(pwd_errors)

        if errors:
            return AuthResult(False, "Error de validación.", errors=errors)

        if self._repo.find_by_username(username):
            return AuthResult(False, "El nombre de usuario ya está en uso.", errors=["Usuario duplicado."])

        if self._repo.find_by_email(email):
            return AuthResult(False, "El correo ya está registrado.", errors=["Email duplicado."])

        # Usamos nuestro PasswordHasher restaurado
        password_hash = PasswordHasher.hash(password)
        
        factory = UserFactoryRegistry.get(role)
        user    = factory.build(username, email, password_hash)

        self._repo.save(user)
        self._event_bus.publish(AuthEvent(AuthEvent.USER_REGISTERED, {
            "user_id":  user.user_id,
            "username": user.username,
            "email":    user.email,
            "role":     user.role,
        }))

        token = self._generate_token(user)
        return AuthResult(True, "Usuario registrado correctamente.", data={**user.to_dict(), "token": token})

    def log_in(self, username: str, password: str) -> AuthResult:
        user = self._repo.find_by_username(username)

        if not user:
            self._event_bus.publish(AuthEvent(AuthEvent.LOGIN_FAILED, {"username": username}))
            # FIJATE ACÁ: No hay coma al final, solo el AuthResult
            return AuthResult(False, "Credenciales incorrectas.", errors=["Usuario no encontrado."])

        if not user.is_active:
            return AuthResult(False, "Cuenta bloqueada. Contactá al administrador.", errors=["Cuenta bloqueada."])

        if not PasswordHasher.verify(password, user.password_hash):
            user.failed_attempts += 1
            if user.failed_attempts >= MAX_FAILED_ATTEMPTS:
                user.is_active = False
                self._event_bus.publish(AuthEvent(AuthEvent.ACCOUNT_LOCKED, {"username": username}))
            else:
                self._event_bus.publish(AuthEvent(AuthEvent.LOGIN_FAILED, {"username": username}))
            self._repo.update(user)
            return AuthResult(False, "Credenciales incorrectas.", errors=["Contraseña incorrecta."])

        user.failed_attempts = 0
        self._repo.update(user)

        self._event_bus.publish(AuthEvent(AuthEvent.LOGIN_SUCCESS, {
            "user_id":  user.user_id,
            "username": user.username,
            "role":     user.role,
        }))

        token = self._generate_token(user)
        return AuthResult(True, "Inicio de sesión exitoso.", data={**user.to_dict(), "token": token})

# ═══════════════════════════════════════════════════════════════
# SECCIÓN 8 ─ REPOSITORIO DE RESERVAS
# ═══════════════════════════════════════════════════════════════

class BookingRepository:
    """Repositorio para gestionar las reservas en Supabase."""
    
    def get_all(self) -> list[dict]:
        """Obtiene todas las reservas del sistema (para el admin)."""
        response = supabase_client.table("bookings").select("*").execute()
        return response.data if response.data else []

    def get_by_username(self, username: str) -> list[dict]:
        """Obtiene solo las reservas de un usuario específico."""
        response = supabase_client.table("bookings").select("*").eq("username", username).execute()
        return response.data if response.data else []

    def create(self, booking_data: dict) -> dict | None:
        """Guarda una nueva reserva en la nube."""
        response = supabase_client.table("bookings").insert(booking_data).execute()
        return response.data[0] if response.data else None
    
class SpaceRepository:
    """Repositorio para leer el catálogo de espacios en Supabase."""
    def get_all(self) -> list[dict]:
        response = supabase_client.table("spaces").select("*").execute()
        return response.data if response.data else []
