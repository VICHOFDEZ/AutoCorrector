import csv
import os
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import pyautogui

from control import (abrir_rubrica_en_respuesta, avanzar_siguiente_alumno, fotografiar_panel,
                     guardar_nota_pregunta, ingresar_evaluacion)
from ia_core import descargar_modelo, evaluar_respuesta, precargar_modelo, verificar_ollama
from lector_pdf import buscar_inciso, procesar_pauta_pdf
from pantalla import cargar_config, configurar_tesseract, ruta_proyecto, zona
from vision import buscar_inicio_pregunta, escanear_respuesta_completa, ir_al_inicio, volver_a_pregunta

MODOS = {"1": "automatico", "2": "confirmar", "3": "simulacion"}
COLUMNAS_CSV = ["fecha", "alumno", "pregunta", "inciso", "puntaje_ia", "puntaje_final", "estado", "justificacion", "imagen"]


def _preguntar(texto, defecto=None):
    sufijo = f" [Enter = {defecto}]" if defecto else ""
    valor = input(f"{texto}{sufijo}: ").strip()
    return valor or (defecto or "")


def _elegir_pauta(config):
    """Lista los PDF de la carpeta 'pautas' y deja elegir uno (Enter = el de config.json)."""
    por_defecto = ruta_proyecto(config["pauta_pdf"])
    carpeta = ruta_proyecto("pautas")
    pdfs = sorted(f for f in os.listdir(carpeta) if f.lower().endswith(".pdf")) if os.path.isdir(carpeta) else []
    if len(pdfs) <= 1:
        return os.path.join(carpeta, pdfs[0]) if pdfs else por_defecto

    print("\n📚 Pautas disponibles en la carpeta 'pautas':")
    for i, nombre in enumerate(pdfs, 1):
        marca = "  (por defecto)" if os.path.join(carpeta, nombre) == os.path.normpath(por_defecto) else ""
        print(f"   {i}) {nombre}{marca}")
    eleccion = input("¿Qué pauta usar? (número, Enter = por defecto): ").strip()
    if eleccion.isdigit() and 1 <= int(eleccion) <= len(pdfs):
        return os.path.join(carpeta, pdfs[int(eleccion) - 1])
    return por_defecto


def _verificaciones_previas(config):
    """Comprueba todo lo que puede fallar ANTES de tocar la pantalla."""
    ok = True
    tesseract = configurar_tesseract()
    if tesseract:
        print(f"✅ Tesseract: {tesseract}")
    else:
        print("❌ Tesseract no está instalado. Descárgalo de https://github.com/UB-Mannheim/tesseract/wiki "
              "y, si lo instalas en otra carpeta, pon la ruta en config.json → ocr.tesseract_cmd")
        ok = False

    ia_ok, mensaje = verificar_ollama()
    print(("✅ " if ia_ok else "❌ ") + mensaje)
    ok = ok and ia_ok

    pauta = procesar_pauta_pdf(_elegir_pauta(config))
    if not pauta:
        print("⚠️ Sin pauta PDF: la IA solo verá la foto del panel de rúbrica (menos preciso).")
    return ok, pauta


def _config_sesion(pauta):
    print("\n📋 Configuración de la sesión:")
    if pauta:
        print("   Preguntas en la pauta: " + ", ".join(
            f"{n} ({', '.join(p['incisos'])})" for n, p in pauta.items()))

    pregunta = _preguntar("1. Número de la pregunta a corregir (ej: 1)").rstrip(".")
    numeros = list(pauta)
    siguiente = numeros[numeros.index(pregunta) + 1] if pregunta in numeros[:-1] else None
    fin = _preguntar("2. Número de la pregunta SIGUIENTE, que marca el fin de la respuesta ('fin' si es la última)",
                     siguiente or "fin").rstrip(".")
    fin = None if fin.lower() == "fin" else fin

    incisos_pauta = ", ".join(pauta[pregunta]["incisos"]) if pregunta in pauta else None
    incisos = [s.strip() for s in _preguntar("3. Incisos a evaluar en el panel (ej: 1a, 1b)", incisos_pauta).split(",")
               if s.strip()]
    if not incisos:
        raise ValueError("Debes indicar al menos un inciso.")

    num_alumnos = int(_preguntar("\n👥 ¿Cuántos alumnos corregir en esta sesión?"))
    modo = MODOS.get(_preguntar("⚙️ Modo: 1) automático  2) confirmar cada nota  3) simulación (no ingresa notas)", "1"),
                     "automatico")
    return pregunta, fin, incisos, num_alumnos, modo


def _decidir_puntaje(inciso, resultado, modo):
    """Devuelve (puntaje_final o None, estado)."""
    puntaje = resultado["puntaje"]
    if modo == "confirmar":
        print(f"\n   {inciso}: IA propone {puntaje} pts — {resultado['justificacion'][:300]}")
        while True:
            respuesta = input("   Enter = aceptar | número = otro puntaje | s = saltar: ").strip().lower()
            if respuesta == "s":
                return None, "SALTADO"
            if not respuesta:
                break
            try:
                return float(respuesta.replace(",", ".")), "CORREGIDO_MANUAL"
            except ValueError:
                print("   Valor no válido.")
    if puntaje is None:
        return None, "REVISAR_ERROR_IA"
    return puntaje, "OK"


def _procesar_alumno(n, ctx, ejecutor, escribir):
    visor, pregunta, fin, incisos, pauta_incisos, modo, carpeta = (
        ctx["visor"], ctx["pregunta"], ctx["fin"], ctx["incisos"], ctx["pauta_incisos"], ctx["modo"], ctx["carpeta"])

    ir_al_inicio(visor)
    linea, img = buscar_inicio_pregunta(visor, pregunta)
    if not linea:
        for inciso in incisos:
            escribir(n, inciso, "", "", "PREGUNTA_NO_ENCONTRADA", "", "")
        return

    ruta_img = os.path.join(carpeta, f"alumno_{n:03d}_p{pregunta}.jpg")
    ruta_img, clicks = escanear_respuesta_completa(visor, linea, img, fin, ruta_img)

    sin_pauta = [i for i in incisos if not (pauta_incisos.get(i) or {}).get("niveles")]
    posicion = volver_a_pregunta(visor, clicks, pregunta) or (
        linea["palabras"][0]["x"] + linea["palabras"][0]["w"] // 2, linea["y"] + linea["h"] // 2)

    if sin_pauta:
        # Hace falta la foto del panel antes de llamar a la IA
        if modo != "simulacion":
            abrir_rubrica_en_respuesta(*posicion)
        paneles = [fotografiar_panel(i, incisos, os.path.join(carpeta, f"alumno_{n:03d}_panel_{i}.jpg"))
                   for i in sin_pauta]
        resultados = evaluar_respuesta(ruta_img, incisos, pauta_incisos, paneles)
    else:
        # La IA trabaja en segundo plano mientras se abre la rúbrica en pantalla
        futuro = ejecutor.submit(evaluar_respuesta, ruta_img, incisos, pauta_incisos)
        if modo != "simulacion":
            abrir_rubrica_en_respuesta(*posicion)
        resultados = futuro.result()

    for inciso in incisos:
        resultado = resultados[inciso]
        puntaje, estado = _decidir_puntaje(inciso, resultado, modo)
        if puntaje is not None and modo != "simulacion":
            if not ingresar_evaluacion(inciso, puntaje, incisos):
                estado = "REVISAR_NO_SE_PUDO_CLIQUEAR"
            elif not guardar_nota_pregunta():
                estado = "REVISAR_NO_SE_GUARDO"
        elif modo == "simulacion":
            estado = "SIMULADO"
        escribir(n, inciso, resultado["puntaje"], puntaje, estado, resultado["justificacion"], ruta_img)


def iniciar_autocorrector():
    print("🚀 INICIANDO AUTOCORRECTOR EMARKING WEBC 🚀\n")
    try:
        config = cargar_config()
        visor = zona("visor_central_prueba")
        coords_siguiente = config["botones_estaticos"]["siguiente_alumno"]
    except Exception as e:
        print(f"❌ Error al cargar config.json: {e}")
        return

    listo, pauta = _verificaciones_previas(config)
    if not listo:
        print("\n⛔ Corrige los errores de arriba y vuelve a ejecutar.")
        return

    try:
        pregunta, fin, incisos, num_alumnos, modo = _config_sesion(pauta)
    except ValueError as e:
        print(f"❌ Dato inválido: {e}")
        return

    pauta_incisos = {i: buscar_inciso(pauta, i) for i in incisos}
    for inciso, datos in pauta_incisos.items():
        if datos:
            print(f"   📘 {inciso}: niveles {[n['puntos'] for n in datos['niveles']]}")
        else:
            print(f"   ⚠️ {inciso}: no está en la pauta, se usará la foto del panel.")

    carpeta = ruta_proyecto(config.get("carpeta_resultados", "resultados"), datetime.now().strftime("%Y%m%d_%H%M%S"))
    os.makedirs(carpeta, exist_ok=True)
    ruta_csv = os.path.join(carpeta, "resultados.csv")

    pyautogui.FAILSAFE = True  # mover el mouse a una esquina de la pantalla detiene todo
    with ThreadPoolExecutor(max_workers=1) as ejecutor, open(ruta_csv, "w", newline="", encoding="utf-8-sig") as f:
        # El modelo se carga mientras el usuario prepara la ventana (antes: se recargaba en cada inciso)
        precarga = ejecutor.submit(precargar_modelo)

        segundos = config["navegacion"]["segundos_preparacion"]
        print(f"\n⚠️ PREPÁRATE: tienes {segundos} s para dejar eMarking maximizado en el primer alumno.")
        print("   (Para abortar en cualquier momento, lleva el mouse a una esquina de la pantalla.)")
        time.sleep(segundos)
        precarga.result()

        csv_writer = csv.writer(f, delimiter=";")
        csv_writer.writerow(COLUMNAS_CSV)
        resumen = {}

        def escribir(n, inciso, puntaje_ia, puntaje_final, estado, justificacion, imagen):
            csv_writer.writerow([datetime.now().isoformat(timespec="seconds"), n, pregunta, inciso,
                                 puntaje_ia, puntaje_final, estado, justificacion, imagen])
            f.flush()
            resumen[estado] = resumen.get(estado, 0) + 1

        ctx = {"visor": visor, "pregunta": pregunta, "fin": fin, "incisos": incisos,
               "pauta_incisos": pauta_incisos, "modo": modo, "carpeta": carpeta}
        try:
            for n in range(1, num_alumnos + 1):
                print(f"\n=========================================")
                print(f"👨‍🎓 ALUMNO {n} DE {num_alumnos}")
                print(f"=========================================")
                inicio = time.time()
                try:
                    _procesar_alumno(n, ctx, ejecutor, escribir)
                except pyautogui.FailSafeException:
                    raise
                except Exception as e:
                    print(f"❌ Error con el alumno {n}: {e}")
                    traceback.print_exc()
                    for inciso in incisos:
                        escribir(n, inciso, "", "", "ERROR", str(e), "")
                print(f"⏱️ Alumno {n} procesado en {time.time() - inicio:.1f} s")
                if n < num_alumnos and not avanzar_siguiente_alumno(coords_siguiente, visor):
                    print("⛔ No se pudo avanzar al siguiente alumno; se detiene el lote.")
                    break
        except pyautogui.FailSafeException:
            print("\n🛑 Detenido manualmente (mouse en la esquina).")
        except KeyboardInterrupt:
            print("\n🛑 Detenido con Ctrl+C.")
        finally:
            descargar_modelo()

    print(f"\n✅ LOTE FINALIZADO. Resumen: {resumen}")
    print(f"📁 Resultados e imágenes en: {carpeta}")
    if any(k.startswith("REVISAR") or k in ("ERROR", "PREGUNTA_NO_ENCONTRADA") for k in resumen):
        print("⚠️ Hay incisos marcados para revisión manual en resultados.csv")


if __name__ == "__main__":
    iniciar_autocorrector()
