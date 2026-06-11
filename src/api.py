"""
=============================================================
  COWORKING SPACE — API REST de Autenticación
  Módulo: api.py
  Framework: Flask
=============================================================
"""

import os
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

from .auth import ( ... ) # El punto le dice "buscá auth en esta misma carpeta src"
    AuthEventBus,
    ConsoleLogger,
    DatabaseObserver,
    EmailNotifier,
    SupabaseUserRepository,
    AuthService,
    BookingRepository,
    SpaceRepository,
)

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, static_folder=SRC_DIR, static_url_path="")
CORS(app, resources={r"/api/*": {"origins": "*"}})

@app.get("/")
def index():
    return send_from_directory(SRC_DIR, "login.html")

# Composición del sistema con Supabase
event_bus = AuthEventBus()
event_bus.subscribe(ConsoleLogger())
event_bus.subscribe(DatabaseObserver())
event_bus.subscribe(EmailNotifier())

repository = SupabaseUserRepository()  # ← 2. Conectamos el repositorio de la nube
auth_service = AuthService(repository=repository, event_bus=event_bus)
booking_repo = BookingRepository()
space_repo = SpaceRepository()

def _require_json_fields(data: dict, *fields: str):
    missing = [f for f in fields if not data.get(f)]
    if missing:
        return False, f"Campos requeridos: {', '.join(missing)}"
    return True, None


@app.post("/api/auth/signup")
def signup():
    data = request.get_json(silent=True) or {}
    ok, err = _require_json_fields(data, "username", "email", "password", "confirm_password")
    if not ok:
        return jsonify({"success": False, "message": err, "errors": [err]}), 400

    result = auth_service.sign_up(
        username=data["username"].strip(),
        email=data["email"].strip().lower(),
        password=data["password"],
        confirm_password=data["confirm_password"],
        role=data.get("role", "member"),
    )
    status_code = 201 if result.success else 400
    return jsonify(result.to_dict()), status_code


@app.post("/api/auth/login")
def login():
    data = request.get_json(silent=True) or {}
    ok, err = _require_json_fields(data, "username", "password")
    if not ok:
        return jsonify({"success": False, "message": err, "errors": [err]}), 400

    result = auth_service.log_in(
        username=data["username"].strip(),
        password=data["password"],
    )
    status_code = 200 if result.success else 401
    return jsonify(result.to_dict()), status_code
@app.get("/api/users")
def get_all_users():
    """Endpoint para que el Dashboard obtenga la lista real de usuarios."""
    users = repository.get_all()
    # Convertimos los objetos a diccionarios, pero ocultamos el password_hash por seguridad
    users_data = []
    for u in users:
        u_dict = u.to_dict()
        users_data.append(u_dict)
        
    return jsonify({
        "success": True, 
        "data": users_data
    }), 200

# --- ENDPOINTS DE RESERVAS ---

@app.post("/api/bookings")
def create_booking():
    data = request.get_json(silent=True) or {}
    ok, err = _require_json_fields(data, "username", "space_name", "booking_date", "booking_time")
    if not ok:
        return jsonify({"success": False, "message": err}), 400

    new_booking = {
        "username": data["username"],
        "space_name": data["space_name"],
        "booking_date": data["booking_date"],
        "booking_time": data["booking_time"],
        "status": "activa"
    }
    
    result = booking_repo.create(new_booking)
    if result:
        return jsonify({"success": True, "message": "Reserva confirmada.", "data": result}), 201
    return jsonify({"success": False, "message": "Error al guardar en BD."}), 500

@app.get("/api/bookings")
def get_bookings():
    username = request.args.get("username")
    reservas = booking_repo.get_by_username(username) if username else booking_repo.get_all()
    return jsonify({"success": True, "data": reservas}), 200

@app.patch("/api/bookings/<booking_id>")
def update_booking_status(booking_id):
    """Permite al admin confirmar o cancelar una reserva (actualiza status en Supabase)."""
    data = request.get_json(silent=True) or {}
    new_status = data.get("status")
    allowed_statuses = {"activa", "cancelada", "pendiente"}
    if not new_status or new_status not in allowed_statuses:
        return jsonify({"success": False, "message": f"Status inválido. Debe ser uno de: {allowed_statuses}"}), 400

    from auth import get_supabase_client
    client = get_supabase_client()
    # Supabase devuelve error si no hay filas actualizadas — lo capturamos
    try:
        response = client.table("bookings").update({"status": new_status}).eq("id", booking_id).execute()
        if response.data:
            return jsonify({"success": True, "data": response.data[0]}), 200
        return jsonify({"success": False, "message": "Reserva no encontrada."}), 404
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.get("/api/spaces")
def get_spaces():
    """Devuelve el catálogo dinámico de espacios desde Supabase."""
    espacios = space_repo.get_all()
    return jsonify({"success": True, "data": espacios}), 200

if __name__ == "__main__":
    app.run(debug=True, port=5000)
