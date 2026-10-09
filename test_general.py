"""Diagnóstico del sistema.

  python test_general.py                        -> revisa config, Tesseract, Ollama y pauta (no toca la pantalla)
  python test_general.py --pantalla 1           -> además prueba OCR del visor/panel y busca la pregunta 1
  python test_general.py --ia foto.jpg 1a 1b    -> evalúa una imagen guardada con la IA (sin eMarking)
"""
import argparse
import os
import time

import pyautogui

from ia_core import evaluar_respuesta, verificar_ollama
from lector_pdf import buscar_inciso, procesar_pauta_pdf
from pantalla import capturar, cargar_config, configurar_tesseract, leer_lineas, ruta_proyecto, zona


def revisar_config():
    config = cargar_config()
    ancho, alto = pyautogui.size()
    print(f"✅ config.json cargado. Pantalla: {ancho}x{alto}")
    for nombre in config["zonas_pantalla"]:
        z = zona(nombre)
        fuera = z["left"] + z["width"] > ancho or z["top"] + z["height"] > alto or z["width"] <= 0 or z["height"] <= 0
        print(f"   {'⚠️' if fuera else '✅'} {nombre}: {z}" + ("  ← fuera de la pantalla, recalibra" if fuera else ""))
    return config


def revisar_pauta(config):
    pauta = procesar_pauta_pdf(ruta_proyecto(config["pauta_pdf"]))
    for pregunta in pauta.values():
        for inciso, datos in pregunta["incisos"].items():
            niveles = [n["puntos"] for n in datos["niveles"]]
            aviso = "" if niveles else "  ⚠️ sin niveles de logro"
            print(f"   {inciso}: niveles {niveles}, solución {len(datos['solucion'])} caracteres{aviso}")
    return pauta


def probar_pantalla(numero):
    from control import _encabezados, _tarjetas_puntaje  # solo diagnóstico
    from vision import buscar_linea_pregunta

    print("\n⚠️ Tienes 5 segundos para dejar eMarking visible...")
    time.sleep(5)
    visor = zona("visor_central_prueba")
    img = capturar(visor)
    img.save(ruta_proyecto("diag_visor.jpg"))
    linea = buscar_linea_pregunta(img, visor, numero)
    print(f"{'✅' if linea else '❌'} Pregunta '{numero}' en el visor: {linea['texto'] if linea else 'no visible'}")

    rubrica = zona(cargar_config()["rubrica"]["zona"])
    capturar(rubrica).save(ruta_proyecto("diag_rubrica.jpg"))
    lineas = leer_lineas(rubrica)
    print(f"📋 Texto del panel de rúbrica ({len(lineas)} líneas):")
    for l in lineas[:25]:
        print(f"   y={l['y']:4d}  {l['texto']}")
    print(f"   Tarjetas de puntaje detectadas: {[(v, x, y) for v, x, y in _tarjetas_puntaje(lineas)]}")
    print(f"   Incisos detectados: {list(_encabezados(lineas, [f'{numero}{c}' for c in 'abcdef'] + [numero]))}")
    print("   (Capturas guardadas en diag_visor.jpg y diag_rubrica.jpg)")


def main():
    parser = argparse.ArgumentParser(description="Diagnóstico del AutoCorrector")
    parser.add_argument("--pantalla", metavar="PREGUNTA", help="probar OCR sobre eMarking buscando esa pregunta")
    parser.add_argument("--ia", nargs="+", metavar=("IMAGEN", "INCISO"), help="evaluar una imagen: --ia foto.jpg 1a 1b")
    args = parser.parse_args()

    print("=== DIAGNÓSTICO DEL AUTOCORRECTOR ===\n")
    config = revisar_config()

    tesseract = configurar_tesseract()
    print(f"{'✅' if tesseract else '❌'} Tesseract: {tesseract or 'NO instalado (ver config.json → ocr.tesseract_cmd)'}")

    ia_ok, mensaje = verificar_ollama()
    print(("✅ " if ia_ok else "❌ ") + mensaje)

    pauta = revisar_pauta(config)

    if args.pantalla:
        if tesseract:
            probar_pantalla(args.pantalla.rstrip("."))
        else:
            print("⏭️ Prueba de pantalla omitida: falta Tesseract.")

    if args.ia:
        imagen, incisos = args.ia[0], args.ia[1:]
        if not os.path.isfile(imagen) or not incisos:
            print("❌ Uso: --ia foto.jpg 1a 1b")
        elif ia_ok:
            resultado = evaluar_respuesta(imagen, incisos, {i: buscar_inciso(pauta, i) for i in incisos})
            for inciso, r in resultado.items():
                print(f"\n📊 {inciso}: {r['puntaje']} pts\n   {r['justificacion']}")


if __name__ == "__main__":
    main()
