"""Navegación del visor de la prueba: ir al inicio, encontrar la pregunta y capturar la respuesta completa."""
import re

import numpy as np
import pyautogui
from PIL import Image

from pantalla import agrupar_lineas, a_gris, capturar, cargar_config, centro, diferencia, esperar_estable, leer_palabras


def _nav():
    return cargar_config()["navegacion"]


def _lineas_visor(img, region):
    # psm 3 (segmentación automática) funciona mejor que psm 11 sobre una hoja de prueba
    return agrupar_lineas(leer_palabras(img, psm=3, desplazamiento=(region["left"], region["top"])))


def _es_inicio_pregunta(linea, numero):
    """True si la línea empieza con el número de la pregunta: '2.', '2)', 'Pregunta 2', '2 Sean...'."""
    texto = linea["texto"].strip().lower()
    if re.match(rf"^(?:pregunta|preg\.?|p)\s*{numero}\b", texto):
        return True
    if re.match(rf"^{numero}\s*[\.\):\-]", texto):
        return True
    # OCR perdió el punto: aceptar solo si el número va solo y le sigue texto en la misma línea
    primera = linea["palabras"][0]["texto"]
    return primera == numero and len(linea["palabras"]) > 1


def buscar_linea_pregunta(img, region, numero, y_min=None):
    """Devuelve la primera línea (más arriba) que inicia la pregunta `numero`, bajo y_min (coordenada de pantalla)."""
    for linea in _lineas_visor(img, region):
        if (y_min is None or linea["y"] >= y_min) and _es_inicio_pregunta(linea, numero):
            return linea
    return None


def ir_al_inicio(region, max_intentos=15):
    """Sube el visor hasta que deja de moverse (tope del documento)."""
    pyautogui.moveTo(*centro(region))
    anterior = capturar(region)
    for _ in range(max_intentos):
        pyautogui.scroll(_nav()["scroll_busqueda"] * 3)
        actual = esperar_estable(region)
        if diferencia(anterior, actual) < 0.8:
            return actual
        anterior = actual
    return anterior


def buscar_inicio_pregunta(region, numero):
    """Baja por el documento hasta ver el inicio de la pregunta.
    Devuelve (linea, imagen_visor) o (None, None) si no aparece."""
    print(f"🔍 Buscando la pregunta '{numero}' en la prueba del alumno...")
    pyautogui.moveTo(*centro(region))
    img = esperar_estable(region)
    for _ in range(_nav()["max_scrolls_busqueda"]):
        linea = buscar_linea_pregunta(img, region, numero)
        if linea:
            print(f"🎯 Pregunta '{numero}' encontrada (Y={linea['y']}).")
            return linea, img
        pyautogui.scroll(-_nav()["scroll_busqueda"])
        nueva = esperar_estable(region)
        if diferencia(img, nueva) < 0.8:
            break  # llegó al final del documento
        img = nueva
    print(f"❌ No se encontró la pregunta '{numero}'.")
    return None, None


def calcular_desplazamiento(img_previa, img_nueva, alto_franja=80):
    """Cuántos píxeles bajó el contenido entre dos capturas.
    0 = no se movió, None = no hay solapamiento reconocible."""
    a = a_gris(img_previa, 4)
    b = a_gris(img_nueva, 4)
    if a.shape != b.shape:
        return None
    if np.abs(a - b).mean() < 0.8:
        return 0
    alto = a.shape[0]
    if alto <= alto_franja * 2:
        return None

    # Franjas con "tinta" (una franja en blanco calza en cualquier parte), empezando por la más baja:
    # una franja en la fila p solo permite detectar desplazamientos d <= p.
    inicios = range(alto - alto_franja, -1, -8)
    con_textura = [p for p in inicios if a[p:p + alto_franja].std() >= 12]
    if not con_textura:
        return None
    paso = max(1, len(con_textura) // 4)
    for p in con_textura[::paso][:4]:
        franja = a[p:p + alto_franja]
        textura = float(np.abs(franja - franja.mean()).mean())
        errores = np.array([np.abs(b[p - d:p - d + alto_franja] - franja).mean() for d in range(1, p + 1)])
        mejor = int(np.argmin(errores))
        lejanos = np.concatenate([errores[:max(0, mejor - 6)], errores[mejor + 7:]])
        segundo = lejanos.min() if lejanos.size else float("inf")
        # el calce debe ser bueno Y único (texto repetido o zonas grises generan calces falsos)
        if errores[mejor] < min(6.0, 0.25 * textura) and segundo > errores[mejor] + 0.3 * textura:
            return mejor + 1
    return None


def escanear_respuesta_completa(region, linea_inicio, img_inicial, numero_fin, ruta_salida):
    """Baja por el visor uniendo capturas (sin duplicar el solapamiento) desde la pregunta
    hasta el inicio de la pregunta `numero_fin` (o el final del documento si es None).
    Devuelve (ruta_imagen, clicks_de_scroll_bajados)."""
    fin_txt = f"pregunta {numero_fin}" if numero_fin else "el final del documento"
    print(f"📸 Capturando la respuesta hasta {fin_txt}...")
    nav = _nav()
    margen = 12
    top = region["top"]

    img = img_inicial
    alto = img.height
    y_desde = max(0, linea_inicio["y"] - top - margen)
    trozos = [np.asarray(img)[y_desde:]]
    altura_total = alto - y_desde
    offset = -y_desde  # fila del lienzo = fila de la captura actual + offset
    y_busqueda = linea_inicio["y"] + linea_inicio["h"]
    clicks = 0
    y_corte = None
    d_esperado = None

    for _ in range(nav["max_capturas_respuesta"]):
        if numero_fin:
            linea_fin = buscar_linea_pregunta(img, region, numero_fin, y_min=y_busqueda)
            if linea_fin:
                y_corte = max(1, linea_fin["y"] - top - 4 + offset)
                print(f"🛑 Inicio de la pregunta {numero_fin} detectado.")
                break

        pyautogui.scroll(-nav["scroll_captura"])
        clicks += nav["scroll_captura"]
        nueva = esperar_estable(region)
        d = calcular_desplazamiento(img, nueva)
        if d == 0:
            print("📄 Fin del documento alcanzado.")
            break
        # Cada scroll mueve lo mismo: si la medición es dudosa, usar la última confiable
        # (solo puede ser menor al llegar al final del documento, nunca mayor).
        if d_esperado and (d is None or d > d_esperado * 1.15):
            d = d_esperado
        elif d is not None and d_esperado is None:
            d_esperado = d
        filas_nuevas = alto if d is None or d >= alto else d
        trozos.append(np.asarray(nueva)[alto - filas_nuevas:])
        altura_total += filas_nuevas
        offset = altura_total - alto
        y_busqueda = None
        img = nueva
    else:
        if numero_fin:
            print(f"⚠️ No se vio la pregunta {numero_fin} tras {nav['max_capturas_respuesta']} capturas; se usa lo capturado.")

    lienzo = np.vstack(trozos)
    if y_corte:
        lienzo = lienzo[:y_corte]
    Image.fromarray(lienzo).save(ruta_salida, quality=92)
    print(f"✅ Respuesta capturada ({lienzo.shape[1]}x{lienzo.shape[0]} px) en {ruta_salida}")
    return ruta_salida, clicks


def volver_a_pregunta(region, clicks, numero):
    """Deshace el scroll de la captura y ubica otra vez el número de la pregunta (para abrir la rúbrica ahí).
    Devuelve (x, y) en pantalla o None."""
    pyautogui.moveTo(*centro(region))
    if clicks:
        pyautogui.scroll(clicks)
    img = esperar_estable(region)
    linea = buscar_linea_pregunta(img, region, numero)
    if not linea:
        return None
    palabra = linea["palabras"][0]
    return palabra["x"] + palabra["w"] // 2, palabra["y"] + palabra["h"] // 2
