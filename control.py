"""Interacción con el panel de rúbrica de eMarking: abrir incisos, marcar puntaje, guardar y avanzar."""
import os
import re
import time

import pyautogui

from pantalla import capturar, cargar_config, centro, esperar_cambio, esperar_estable, leer_lineas, ruta_proyecto, zona

_UNIDAD = r"(?:pts?|ptos?|puntos?)\.?"


def _rub():
    return cargar_config()["rubrica"]


def _zona_rubrica():
    return zona(_rub()["zona"])


def _clic(x, y):
    pyautogui.moveTo(x, y, duration=0.15)
    pyautogui.click()


def abrir_rubrica_en_respuesta(x, y):
    print(f"🖱️ Abriendo rúbrica sobre la respuesta (X:{x}, Y:{y})...")
    _clic(x, y)
    esperar_estable(_zona_rubrica(), timeout=3)


# ---------------------------------------------------------------- Lectura del panel

def _patron_inciso(inciso):
    m = re.fullmatch(r"(\d+)\s*([a-z]?)", re.sub(r"[^0-9a-z]", "", inciso.lower()))
    if not m:
        return re.compile(re.escape(inciso.lower()))
    num, letra = m.groups()
    if letra:
        return re.compile(rf"(?<![0-9a-z]){num}\s*[\.\-]?\s*\(?{letra}\)?(?![a-z0-9])")
    # sin letra: el número no debe ser un puntaje ("3 pts")
    return re.compile(rf"(?<![0-9a-z.,]){num}(?![0-9.,]|\s*{_UNIDAD}(?![a-z]))")


def _encabezados(lineas, incisos):
    """{inciso: linea} para los incisos visibles en el panel (primera aparición)."""
    encontrados = {}
    for inciso in incisos:
        patron = _patron_inciso(inciso)
        for linea in lineas:
            if patron.search(linea["texto"].lower()):
                encontrados[inciso] = linea
                break
    return encontrados


def _tarjetas_puntaje(lineas):
    """Lista de (valor, x, y) de cada 'N pts' visible."""
    tarjetas = []
    for linea in lineas:
        palabras = linea["palabras"]
        for i, p in enumerate(palabras):
            t = p["texto"].lower()
            m = re.fullmatch(rf"(\d+(?:[.,]\d+)?)({_UNIDAD})?", t)
            if not m:
                continue
            tiene_unidad = m.group(2) or (i + 1 < len(palabras) and re.fullmatch(_UNIDAD, palabras[i + 1]["texto"].lower()))
            if tiene_unidad:
                valor = float(m.group(1).replace(",", "."))
                tarjetas.append((valor, p["x"] + p["w"] // 2, p["y"] + p["h"] // 2))
    return tarjetas


def _tarjetas_de_inciso(lineas, inciso, incisos):
    """Tarjetas de puntaje que están entre el encabezado del inciso y el encabezado siguiente."""
    enc = _encabezados(lineas, incisos)
    if inciso not in enc:
        return None, []
    y_ini = enc[inciso]["y"] + enc[inciso]["h"]
    y_fin = min((l["y"] for k, l in enc.items() if k != inciso and l["y"] > y_ini), default=float("inf"))
    tarjetas = [t for t in _tarjetas_puntaje(lineas) if y_ini < t[2] < y_fin]
    return enc[inciso], tarjetas


def _buscar_encabezado(inciso, incisos, region):
    """Lee el panel y, si el inciso no está visible, lo busca haciendo scroll dentro del panel."""
    lineas = leer_lineas(region)
    if inciso in _encabezados(lineas, incisos):
        return lineas
    pyautogui.moveTo(*centro(region))
    pyautogui.scroll(3000)  # tope del panel
    for _ in range(4):
        esperar_estable(region)
        lineas = leer_lineas(region)
        if inciso in _encabezados(lineas, incisos):
            return lineas
        pyautogui.scroll(-400)
    return None


def fotografiar_panel(inciso, incisos, ruta_salida):
    """Solo para incisos sin pauta en el PDF: abre el inciso y guarda una foto del panel de rúbrica."""
    region = _zona_rubrica()
    lineas = _buscar_encabezado(inciso, incisos, region)
    if lineas:
        encabezado, tarjetas = _tarjetas_de_inciso(lineas, inciso, incisos)
        if not tarjetas:
            _clic(encabezado["x"] + 10, encabezado["y"] + encabezado["h"] // 2)
            esperar_estable(region)
    capturar(region).save(ruta_salida)
    return ruta_salida


# ---------------------------------------------------------------- Acciones

def _formatear(valor):
    return str(int(valor)) if float(valor).is_integer() else str(valor)


def ingresar_evaluacion(inciso, puntaje, incisos):
    """Abre el inciso en el panel (si está cerrado) y hace clic en la tarjeta con el puntaje.
    Solo considera tarjetas bajo ese inciso, para no marcar la de otro. Devuelve True si hizo clic."""
    print(f"🖱️ Ingresando {_formatear(puntaje)} pts en '{inciso}'...")
    region = _zona_rubrica()
    desfase_y = _rub()["desfase_clic_puntaje_y"]

    lineas = _buscar_encabezado(inciso, incisos, region)
    if not lineas:
        print(f"❌ No se encontró el inciso '{inciso}' en el panel de rúbrica.")
        return False

    encabezado, tarjetas = _tarjetas_de_inciso(lineas, inciso, incisos)
    if not tarjetas:  # acordeón cerrado: abrirlo
        _clic(encabezado["x"] + 10, encabezado["y"] + encabezado["h"] // 2)
        esperar_estable(region)
        lineas = leer_lineas(region)
        encabezado, tarjetas = _tarjetas_de_inciso(lineas, inciso, incisos)

    for intento in range(4):
        candidatas = [t for t in tarjetas if abs(t[0] - float(puntaje)) < 1e-6]
        if candidatas:
            _, x, y = min(candidatas, key=lambda t: t[2])
            _clic(x, y + desfase_y)
            print(f"✅ Clic en {_formatear(puntaje)} pts.")
            esperar_estable(region, timeout=2)
            return True
        # la tarjeta puede estar más abajo: bajar el panel y volver a leer
        pyautogui.moveTo(*centro(region))
        pyautogui.scroll(-300)
        esperar_estable(region)
        lineas = leer_lineas(region)
        encabezado, tarjetas = _tarjetas_de_inciso(lineas, inciso, incisos)
        if encabezado is None:  # el encabezado salió de la vista: todo lo visible es del inciso hasta el siguiente
            otros = _encabezados(lineas, incisos)
            y_fin = min((l["y"] for l in otros.values()), default=float("inf"))
            tarjetas = [t for t in _tarjetas_puntaje(lineas) if t[2] < y_fin]

    print(f"❌ No se encontró la tarjeta de {_formatear(puntaje)} pts para '{inciso}'.")
    return False


def _buscar_texto(texto, regiones):
    for region in regiones:
        for linea in leer_lineas(region):
            for p in linea["palabras"]:
                if texto in p["texto"].lower():
                    return p["x"] + p["w"] // 2, p["y"] + p["h"] // 2
    return None


def guardar_nota_pregunta():
    """Hace clic en 'Guardar'. Usa la imagen de referencia si existe; si no, lo busca por OCR."""
    rub = _rub()
    posicion = None
    ruta_img = ruta_proyecto(rub.get("imagen_boton_guardar") or "")
    if os.path.isfile(ruta_img):
        try:
            try:
                import cv2  # noqa: F401  (necesario para 'confidence')
                posicion = pyautogui.locateCenterOnScreen(ruta_img, confidence=0.8)
            except ImportError:
                posicion = pyautogui.locateCenterOnScreen(ruta_img)
        except Exception:
            posicion = None
    if posicion is None:
        regiones = [_zona_rubrica(), zona("modal_central_emergente"), None]
        posicion = _buscar_texto(rub.get("texto_boton_guardar", "guardar").lower(), regiones)
    if posicion is None:
        print("❌ No se encontró el botón 'Guardar'.")
        return False
    _clic(*posicion)
    print("💾 Guardado.")
    time.sleep(0.5)
    esperar_estable(_zona_rubrica(), timeout=3)
    return True


def avanzar_siguiente_alumno(coords_siguiente, region_visor):
    """Clic en 'Siguiente' y espera a que el visor cambie (en vez de un sleep fijo)."""
    print("⏭️ Pasando al siguiente alumno...")
    referencia = capturar(region_visor)
    _clic(coords_siguiente["x"], coords_siguiente["y"])
    espera = cargar_config()["navegacion"]["espera_max_siguiente_alumno"]
    if not esperar_cambio(region_visor, referencia, timeout=espera):
        print("⚠️ El visor no cambió; puede que no haya más alumnos o que la carga sea lenta.")
        return False
    return True
