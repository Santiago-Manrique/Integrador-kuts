import csv
import os
from supabase import create_client, Client

# Usamos las credenciales de tu proyecto original (auth.py)
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://kyjszgpgyykktbhsqqjg.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "sb_publishable_7XJYNkkzzbg7HZC7bEqv3w_zxFFxd8U")

def exportar_metricas():
    print("Iniciando exportación de métricas para Estadística...")
    try:
        # Nos conectamos a tu base de datos en la nube
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        response = supabase.table("bookings").select("*").execute()
        reservas = response.data
        
        if not reservas:
            print("No hay reservas guardadas para exportar.")
            return

        nombre_archivo = "reservas_metricas.csv"
        
        with open(nombre_archivo, mode='w', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            
            # --- MEJORA: Exportación Estadística ---
            # Agregamos duracion_horas (cuantitativa continua) y concurrencia_pico (cuantitativa discreta)
            writer.writerow(["id_reserva", "usuario", "tipo_espacio", "fecha", "hora", "estado", "duracion_horas", "concurrencia_pico"])
            
            for r in reservas:
                espacio = r.get("space_name", "")
                
                # Simulamos las variables para la materia en base al tipo de espacio
                duracion = 3.5 if "Reuniones" in espacio else 1.5
                concurrencia = 12 if "Reuniones" in espacio else 1
                
                writer.writerow([
                    r.get("id", "N/A"),
                    r.get("username", "N/A"),
                    espacio,
                    r.get("booking_date", "N/A"),
                    r.get("booking_time", "N/A"),
                    r.get("status", "activa"),
                    duracion,
                    concurrencia
                ])
                
        print(f"¡Listo! Archivo {nombre_archivo} creado con éxito con {len(reservas)} reservas.")
    except Exception as e:
        print(f"Hubo un error al conectar con Supabase: {e}")

if __name__ == "__main__":
    exportar_metricas()
