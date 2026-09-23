import json
import time
from lector_pdf import procesar_pauta_pdf
from vision import buscar_inicio_pregunta, escanear_respuesta_completa
from ia_core import evaluar_respuesta

def ejecutar_prueba_diagnostico():
    print("=== INICIANDO DIAGNÓSTICO DEL SISTEMA (FASES 1-4) ===")
    
    # FASE 1: Leer configuración espacial
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
        coords_visor = config["zonas_pantalla"]["visor_central_prueba"]
        print("✅ Fase 1 OK: Coordenadas del visor cargadas.")
    except Exception as e:
        print(f"❌ Error en Fase 1 (Revisa tu config.json): {e}")
        return

    # FASE 2: Leer Pauta de Evaluación
    # Asegúrate de tener el archivo PDF en esta ruta exacta
    ruta_pdf = "pautas/pauta_prueba.pdf" 
    pauta_estructurada = procesar_pauta_pdf(ruta_pdf)
    
    if not pauta_estructurada:
        print("❌ Error en Fase 2: No se pudo extraer la pauta. ¿Existe el PDF?")
        return
    print(f"✅ Fase 2 OK: Pauta leída con {len(pauta_estructurada)} preguntas.")

    # FASE 3: Visión y Scroll
    print("\n⚠️ TIENES 5 SEGUNDOS PARA MAXIMIZAR LA VENTANA DE EMARKING...")
    time.sleep(5)
    
    # Probaremos simulando que evaluamos la primera pregunta
    pregunta_prueba = pauta_estructurada[0]
    
    # 3.A Búsqueda (Seek): Bajar hasta encontrar el título de la pregunta
    encontrada = buscar_inicio_pregunta(coords_visor, pregunta_prueba['id_pregunta'])
    if not encontrada:
        print("❌ Saliendo de la prueba: La cámara no encontró el título y se perdieron los intentos de scroll.")
        return
        
    # 3.B Captura (Record): Bajar ensamblando fotos hasta la siguiente pregunta
    ruta_imagen = escanear_respuesta_completa(coords_visor, pregunta_prueba['marcador_fin'])
    print("✅ Fase 3 OK: Imagen del desarrollo ensamblada correctamente.")

    # FASE 4: Evaluación con LLaVA
    print("\n🧠 Fase 4: Enviando imagen ensamblada y pauta a Ollama...")
    resultado_ia = evaluar_respuesta(ruta_imagen, pregunta_prueba['pauta'])
    print(f"\n📊 RESULTADO FINAL DEVUELTO POR LA IA: {resultado_ia}")

if __name__ == "__main__":
    ejecutar_prueba_diagnostico()