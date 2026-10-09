"""Evaluación con un modelo de visión local (Ollama) comparando la respuesta del alumno con la pauta."""
import base64
import io
import json
import math
import re
import time

import requests
from PIL import Image, ImageOps

from pantalla import cargar_config


def _cfg():
    return cargar_config()["ia"]


def _url(ruta):
    return _cfg()["url_ollama"].rstrip("/") + ruta


# ---------------------------------------------------------------- Gestión del modelo

def verificar_ollama():
    """(ok, mensaje). Comprueba que Ollama responda y que el modelo esté descargado."""
    modelo = _cfg()["modelo"]
    try:
        r = requests.get(_url("/api/tags"), timeout=5)
        r.raise_for_status()
    except requests.RequestException:
        return False, f"Ollama no responde en {_cfg()['url_ollama']}. Ábrelo o ejecuta 'ollama serve'."
    nombres = {m["name"] for m in r.json().get("models", [])}
    if modelo not in nombres and f"{modelo}:latest" not in nombres:
        disponibles = ", ".join(sorted(nombres)) or "ninguno"
        return False, f"El modelo '{modelo}' no está descargado (tienes: {disponibles}). Ejecuta: ollama pull {modelo}"
    return True, f"Ollama OK, modelo '{modelo}' disponible."


def precargar_modelo():
    """Carga el modelo en memoria una sola vez (con messages vacío Ollama solo lo carga)."""
    try:
        requests.post(_url("/api/chat"), json={"model": _cfg()["modelo"], "messages": [],
                                                "keep_alive": _cfg()["keep_alive"]}, timeout=_cfg()["timeout_segundos"])
        print("🧠 Modelo de IA cargado en memoria.")
    except requests.RequestException as e:
        print(f"⚠️ No se pudo precargar el modelo: {e}")


def descargar_modelo():
    """Libera la VRAM al terminar la sesión."""
    try:
        requests.post(_url("/api/chat"), json={"model": _cfg()["modelo"], "messages": [], "keep_alive": 0}, timeout=10)
    except requests.RequestException:
        pass


# ---------------------------------------------------------------- Imágenes

def preparar_imagenes(ruta_imagen):
    """Recorta márgenes en blanco y divide una captura alta en trozos legibles.
    (Antes se reducía todo a 800 px de lado mayor: una respuesta de 3000 px de alto quedaba ilegible.)"""
    cfg = _cfg()
    ancho_max, alto_trozo, max_trozos = cfg["ancho_max_imagen"], cfg["alto_trozo_imagen"], cfg["max_trozos"]
    solape = 60

    with Image.open(ruta_imagen) as original:
        img = original.convert("RGB")

    tinta = ImageOps.invert(ImageOps.grayscale(img)).point(lambda v: 255 if v > 40 else 0)
    caja = tinta.getbbox()
    if caja:
        x0, y0, x1, y1 = caja
        img = img.crop((max(0, x0 - 10), max(0, y0 - 10), min(img.width, x1 + 10), min(img.height, y1 + 10)))

    escala = min(1.0, ancho_max / img.width)
    trozos_necesarios = math.ceil(img.height * escala / alto_trozo)
    if trozos_necesarios > max_trozos:
        escala *= max_trozos / trozos_necesarios
    if escala < 1.0:
        img = img.resize((max(1, int(img.width * escala)), max(1, int(img.height * escala))), Image.LANCZOS)

    trozos = []
    y = 0
    while y < img.height:
        trozo = img.crop((0, y, img.width, min(img.height, y + alto_trozo)))
        buffer = io.BytesIO()
        trozo.save(buffer, format="JPEG", quality=88)
        trozos.append(base64.b64encode(buffer.getvalue()).decode("utf-8"))
        if y + alto_trozo >= img.height:
            break
        y += alto_trozo - solape
    return trozos


def _imagen_b64(ruta):
    with Image.open(ruta) as img:
        buffer = io.BytesIO()
        img.convert("RGB").save(buffer, format="JPEG", quality=88)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


# ---------------------------------------------------------------- Prompt

SISTEMA = (
    "Eres un ayudante universitario que corrige pruebas de matemáticas escritas a mano. "
    "Comparas el desarrollo del estudiante con la pauta oficial y asignas exactamente uno de los "
    "niveles de logro permitidos. No inventas contenido que no aparece en las imágenes. "
    "Aceptas procedimientos distintos a la pauta si son matemáticamente correctos y completos. "
    "Si la respuesta está en blanco o no aborda el problema, asignas el nivel de 0 puntos."
)


def _bloque_inciso(inciso, datos):
    if not datos or not datos.get("niveles"):
        return (f"### Inciso {inciso}\n(No hay pauta escrita para este inciso: lee sus niveles de logro "
                f"en la imagen del panel de rúbrica, que va al final.)\n")
    niveles = "\n".join(f"- {n['puntos']} pts (Nivel {n['nivel']}): {n['descripcion']}" for n in datos["niveles"])
    partes = [f"### Inciso {inciso}"]
    if datos.get("contexto"):
        partes.append(f"Contexto de la pregunta:\n{datos['contexto']}")
    partes.append(f"Enunciado:\n{datos['enunciado']}")
    if datos.get("solucion"):
        partes.append(f"Solución de la pauta:\n{datos['solucion']}")
    partes.append(f"Niveles de logro (elige uno):\n{niveles}")
    return "\n\n".join(partes) + "\n"


def _construir_prompt(incisos, pauta_incisos, n_trozos, n_paneles):
    paneles = f" Las últimas {n_paneles} imágenes son fotos del panel de rúbrica de eMarking." if n_paneles else ""
    return (
        f"Las primeras {n_trozos} imágenes son, en orden de arriba hacia abajo, el desarrollo del estudiante "
        f"(trozos consecutivos de la misma hoja, con un leve solapamiento).{paneles}\n\n"
        "Para cada inciso: 1) resume lo que el estudiante escribió para ese inciso, 2) compáralo con la "
        "solución de la pauta indicando qué pasos están correctos, cuáles faltan y cuáles tienen errores, "
        "3) elige el nivel de logro que mejor describe el desarrollo y entrega su puntaje exacto.\n\n"
        + "\n".join(_bloque_inciso(i, pauta_incisos.get(i)) for i in incisos)
    )


def _esquema(incisos, pauta_incisos):
    propiedades = {}
    for inciso in incisos:
        puntaje = {"type": "number"}
        niveles = (pauta_incisos.get(inciso) or {}).get("niveles")
        if niveles:
            puntaje["enum"] = [n["puntos"] for n in niveles]
        propiedades[inciso] = {
            "type": "object",
            "properties": {
                "lo_que_escribio": {"type": "string"},
                "comparacion_con_pauta": {"type": "string"},
                "puntaje": puntaje,
            },
            "required": ["lo_que_escribio", "comparacion_con_pauta", "puntaje"],
        }
    return {"type": "object", "properties": propiedades, "required": list(incisos)}


def _ajustar_a_nivel(valor, niveles):
    """Lleva el puntaje al nivel permitido más cercano (la IA a veces devuelve valores intermedios)."""
    if not niveles:
        return valor
    permitidos = [n["puntos"] for n in niveles]
    return min(permitidos, key=lambda p: abs(p - valor))


def _extraer_json(texto):
    texto = texto.strip()
    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", texto, re.S)
        if m:
            return json.loads(m.group(0))
        raise


# ---------------------------------------------------------------- Evaluación

def evaluar_respuesta(ruta_img_respuesta, incisos, pauta_incisos, rutas_paneles=()):
    """Evalúa TODOS los incisos en una sola llamada (las imágenes se procesan una vez, no una por inciso).
    Devuelve {inciso: {"puntaje": número o None, "justificacion": str}}.
    puntaje = None significa que la IA falló: ese inciso queda para revisión manual (antes se ingresaba 0)."""
    cfg = _cfg()
    trozos = preparar_imagenes(ruta_img_respuesta)
    paneles = [_imagen_b64(r) for r in rutas_paneles]
    payload = {
        "model": cfg["modelo"],
        "messages": [
            {"role": "system", "content": SISTEMA},
            {"role": "user", "content": _construir_prompt(incisos, pauta_incisos, len(trozos), len(paneles)),
             "images": trozos + paneles},
        ],
        "stream": False,
        "format": _esquema(incisos, pauta_incisos),
        "keep_alive": cfg["keep_alive"],
        "options": {"temperature": 0, "num_ctx": cfg["num_ctx"]},
    }

    print(f"🧠 Evaluando {', '.join(incisos)} con {cfg['modelo']} ({len(trozos)} trozos de imagen)...")
    inicio = time.time()
    for intento in range(1, cfg["reintentos"] + 1):
        try:
            r = requests.post(_url("/api/chat"), json=payload, timeout=cfg["timeout_segundos"])
            if r.status_code == 404:
                print(f"❌ Ollama no encuentra el modelo '{cfg['modelo']}'. Ejecuta: ollama pull {cfg['modelo']}")
                break
            r.raise_for_status()
            datos = _extraer_json(r.json()["message"]["content"])
            resultado = {}
            for inciso in incisos:
                item = datos.get(inciso) or {}
                niveles = (pauta_incisos.get(inciso) or {}).get("niveles")
                try:
                    puntaje = _ajustar_a_nivel(float(item["puntaje"]), niveles)
                except (KeyError, TypeError, ValueError):
                    puntaje = None
                resultado[inciso] = {
                    "puntaje": puntaje,
                    "justificacion": f"{item.get('lo_que_escribio', '')} | {item.get('comparacion_con_pauta', '')}".strip(" |"),
                }
            print(f"✅ IA respondió en {time.time() - inicio:.1f} s: "
                  + ", ".join(f"{i}={v['puntaje']}" for i, v in resultado.items()))
            return resultado
        except (requests.RequestException, ValueError, KeyError) as e:
            print(f"⚠️ Fallo de la IA (intento {intento}/{cfg['reintentos']}): {e}")
            time.sleep(3)
    return {i: {"puntaje": None, "justificacion": "Error de IA: revisar manualmente"} for i in incisos}
