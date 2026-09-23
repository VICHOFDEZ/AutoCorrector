import json
import time
import pyautogui
import os
from lector_pdf import procesar_pauta_pdf
from vision import buscar_inicio_pregunta, escanear_respuesta_completa
from ia_core import evaluar_respuesta
from control import abrir_rubrica_en_respuesta, ingresar_evaluacion, guardar_nota_pregunta, avanzar_siguiente_alumno, fotografiar_acordeon

def iniciar_autocorrector():
    print("🚀 INICIANDO AUTOCORRECTOR EMARKING WEBC 🚀")
    
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
        coords_visor = config["zonas_pantalla"]["visor_central_prueba"]
        coords_siguiente = config["botones_estaticos"]["siguiente_alumno"]
    except Exception as e:
        print(f"❌ Error al cargar config.json: {e}")
        return

    print("\n📋 Configuración de la sesión:")
    preg_papel = input("1. ¿Qué número buscaremos en el papel del alumno? (ej: 1): ")
    marcador_fin = input("2. ¿Qué texto marca el fin de la respuesta? (ej: 2. o Fin): ")
    
    seleccion_sub = input("3. ¿Qué incisos evaluaremos en el panel derecho? (ej: 1a, 1b): ")
    incisos = [s.strip() for s in seleccion_sub.split(",")]
    
    try:
        num_alumnos = int(input("\n👥 ¿Cuántos alumnos deseas corregir en esta sesión?: "))
    except ValueError:
        return
    
    print("\n⚠️ PREPÁRATE: Tienes 10 segundos para maximizar Emarking.")
    time.sleep(10)

    # ... (código superior de main.py intacto hasta el bucle for alumno) ...
    for alumno in range(1, num_alumnos + 1):
        print(f"\n=========================================")
        print(f"👨‍🎓 EVALUANDO ALUMNO {alumno} DE {num_alumnos}")
        print(f"=========================================")
        
        print("⏩ Posicionando visor al inicio...")
        centro_x = coords_visor["top_left_x"] + (coords_visor["bottom_right_x"] - coords_visor["top_left_x"]) // 2
        pyautogui.moveTo(centro_x, coords_visor["top_left_y"] + 50)
        pyautogui.scroll(-2000) 
        time.sleep(1.5)
        
        encontrada, x, y = buscar_inicio_pregunta(coords_visor, preg_papel + ".")
        if not encontrada:
            print("⚠️ Pregunta no encontrada. Saltando...")
            avanzar_siguiente_alumno(coords_siguiente)
            continue
            
        ruta_img_desarrollo = escanear_respuesta_completa(coords_visor, marcador_fin)
        abrir_rubrica_en_respuesta(x, y)
        
        # --- NUEVA ARQUITECTURA DESACOPLADA ---
        
        # FASE 1: Recopilación visual
        print("\n--- INICIANDO FASE 1: RECOPILACIÓN VISUAL ---")
        fotos_rubricas = {}
        for inciso in incisos:
            ruta_panel = fotografiar_acordeon(inciso)
            fotos_rubricas[inciso] = ruta_panel
            
        # FASE 2: Procesamiento IA en lote
        print("\n--- INICIANDO FASE 2: ANÁLISIS DE IA ---")
        notas_calculadas = {}
        for inciso, ruta_panel in fotos_rubricas.items():
            print(f"\n🧠 Evaluando inciso {inciso}...")
            resultado_ia = evaluar_respuesta(ruta_img_desarrollo, ruta_panel)
            notas_calculadas[inciso] = resultado_ia.get("puntaje", 0)
            
        # FASE 3: Interacción física
        print("\n--- INICIANDO FASE 3: INGRESO DE NOTAS ---")
        for inciso, puntaje in notas_calculadas.items():
            ingresar_evaluacion(inciso, puntaje)
            guardar_nota_pregunta()
                
        avanzar_siguiente_alumno(coords_siguiente)
            
    print("\n✅ LOTE DE CORRECCIÓN FINALIZADO EXITOSAMENTE.")

if __name__ == "__main__":
    iniciar_autocorrector()