"""Utilidades compartidas: configuración, captura de pantalla, OCR y espera de estabilidad."""
import json
import os
import shutil
import threading
import time

import mss
import numpy as np
import pytesseract
from PIL import Image, ImageOps

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RUTA_CONFIG = os.path.join(BASE_DIR, "config.json")

RUTAS_TESSERACT = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
]

_config = None
_local = threading.local()


def cargar_config():
    """Lee config.json una sola vez (siempre desde la carpeta del proyecto, no desde el cwd)."""
    global _config
    if _config is None:
        with open(RUTA_CONFIG, "r", encoding="utf-8") as f:
            _config = json.load(f)
    return _config


def ruta_proyecto(*partes):
    return os.path.join(BASE_DIR, *partes)


def configurar_tesseract():
    """Busca tesseract.exe (config, PATH o rutas típicas). Devuelve la ruta encontrada o None."""
    candidatos = [cargar_config().get("ocr", {}).get("tesseract_cmd"), shutil.which("tesseract"), *RUTAS_TESSERACT]
    for ruta in candidatos:
        if ruta and os.path.isfile(ruta):
            pytesseract.pytesseract.tesseract_cmd = ruta
            return ruta
    return None


def zona(nombre):
    """Convierte una zona de config.json al formato de región de mss."""
    z = cargar_config()["zonas_pantalla"][nombre]
    return {
        "left": z["top_left_x"],
        "top": z["top_left_y"],
        "width": z["bottom_right_x"] - z["top_left_x"],
        "height": z["bottom_right_y"] - z["top_left_y"],
    }


def centro(region):
    return region["left"] + region["width"] // 2, region["top"] + region["height"] // 2


# ---------------------------------------------------------------- Captura

def _mss():
    # mss en Windows no es seguro entre hilos: una instancia reutilizable por hilo.
    if not hasattr(_local, "sct"):
        _local.sct = mss.mss()
    return _local.sct


def capturar(region=None):
    """Captura una región {left, top, width, height} (o el monitor principal completo)."""
    sct = _mss()
    shot = sct.grab(region or sct.monitors[1])
    return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")


def a_gris(img, paso_x=1):
    return np.asarray(ImageOps.grayscale(img), dtype=np.float32)[:, ::paso_x]


def diferencia(img1, img2):
    """Diferencia media (0-255) entre dos capturas del mismo tamaño."""
    if img1.size != img2.size:
        return 255.0
    return float(np.abs(a_gris(img1, 4) - a_gris(img2, 4)).mean())


def esperar_estable(region, timeout=3.0, intervalo=0.15, umbral=0.8):
    """Espera a que la región deje de cambiar (fin de scroll suave, carga, animaciones)."""
    time.sleep(0.1)
    anterior = capturar(region)
    limite = time.time() + timeout
    while time.time() < limite:
        time.sleep(intervalo)
        actual = capturar(region)
        if diferencia(anterior, actual) < umbral:
            return actual
        anterior = actual
    return anterior


def esperar_cambio(region, referencia, timeout=10.0, umbral=3.0):
    """Espera a que la región cambie respecto a `referencia`. Devuelve True si cambió."""
    limite = time.time() + timeout
    while time.time() < limite:
        time.sleep(0.25)
        if diferencia(referencia, capturar(region)) > umbral:
            esperar_estable(region)
            return True
    return False


# ---------------------------------------------------------------- OCR

def leer_palabras(img, psm=11, desplazamiento=(0, 0)):
    """OCR de la imagen. Devuelve palabras con su caja en coordenadas de pantalla
    (si se entrega `desplazamiento` = esquina superior izquierda de la región)."""
    cfg = cargar_config().get("ocr", {})
    escala = cfg.get("escala", 2)
    gris = ImageOps.grayscale(img)
    if np.asarray(gris).mean() < 110:  # interfaz en modo oscuro: Tesseract lee mejor texto oscuro sobre claro
        gris = ImageOps.invert(gris)
    if escala != 1:
        gris = gris.resize((int(gris.width * escala), int(gris.height * escala)), Image.LANCZOS)

    datos = pytesseract.image_to_data(
        gris, lang=cfg.get("idioma", "eng"), config=f"--psm {psm}", output_type=pytesseract.Output.DICT
    )
    dx, dy = desplazamiento
    palabras = []
    for i, texto in enumerate(datos["text"]):
        texto = texto.strip()
        if not texto or float(datos["conf"][i]) < 0:
            continue
        palabras.append({
            "texto": texto,
            "x": int(datos["left"][i] / escala) + dx,
            "y": int(datos["top"][i] / escala) + dy,
            "w": int(datos["width"][i] / escala),
            "h": int(datos["height"][i] / escala),
        })
    return palabras


def agrupar_lineas(palabras):
    """Agrupa palabras en líneas por posición geométrica (más robusto que las líneas de Tesseract,
    sobre todo con --psm 11). Separa tarjetas lado a lado si hay un hueco horizontal grande."""
    filas = []
    for p in sorted(palabras, key=lambda p: p["y"] + p["h"] / 2):
        cy = p["y"] + p["h"] / 2
        if filas:
            fila = filas[-1]
            cy_fila = sum(q["y"] + q["h"] / 2 for q in fila) / len(fila)
            alto = max(max(q["h"] for q in fila), p["h"])
            if abs(cy - cy_fila) <= alto * 0.6:
                fila.append(p)
                continue
        filas.append([p])

    lineas = []
    for fila in filas:
        fila.sort(key=lambda p: p["x"])
        actual = [fila[0]]
        for p in fila[1:]:
            previo = actual[-1]
            if p["x"] - (previo["x"] + previo["w"]) > 3 * max(previo["h"], p["h"], 8):
                lineas.append(_crear_linea(actual))
                actual = []
            actual.append(p)
        lineas.append(_crear_linea(actual))
    return sorted(lineas, key=lambda l: (l["y"], l["x"]))


def _crear_linea(palabras):
    x0 = min(p["x"] for p in palabras)
    y0 = min(p["y"] for p in palabras)
    x1 = max(p["x"] + p["w"] for p in palabras)
    y1 = max(p["y"] + p["h"] for p in palabras)
    return {
        "texto": " ".join(p["texto"] for p in palabras),
        "palabras": palabras,
        "x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0,
    }


def leer_lineas(region, psm=11):
    """Captura la región (None = pantalla completa) y devuelve sus líneas en coordenadas absolutas."""
    region = region or _mss().monitors[1]
    img = capturar(region)
    return agrupar_lineas(leer_palabras(img, psm, (region["left"], region["top"])))
