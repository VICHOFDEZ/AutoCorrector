import requests
import json
import base64
import time
import io
from PIL import Image

def comprimir_imagen_base64(ruta_imagen, max_dim=800):
    try:
        with Image.open(ruta_imagen) as img:
            img = img.convert('RGB')
            img.thumbnail((max_dim, max_dim)) # Reduce tamaño agresivamente
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=80)
            return base64.b64encode(buffer.getvalue()).decode('utf-8')
    except Exception as e:
        print(f"❌ Error al comprimir {ruta_imagen}: {e}")
        return None

def evaluar_respuesta(ruta_img_respuesta, ruta_img_panel):
    print("🧠 Analizando con IA (La VRAM se vaciará al terminar)...")
    
    base64_respuesta = comprimir_imagen_base64(ruta_img_respuesta)
    base64_panel = comprimir_imagen_base64(ruta_img_panel)
    
    if not base64_respuesta or not base64_panel:
        return {"puntaje": 0}

    prompt = """Eres un estricto ayudante universitario. Te envío dos imágenes:
    - IMAGEN 1: El desarrollo matemático del estudiante.
    - IMAGEN 2: El panel con las tarjetas de la rúbrica oficial.
    
    Reglas estrictas:
    1. Lee la rúbrica directamente de la IMAGEN 2.
    2. Evalúa la IMAGEN 1 basándote ÚNICAMENTE en las condiciones de la IMAGEN 2.
    3. Tu respuesta final debe ser SOLO un objeto JSON válido, sin texto adicional.
    
    Formato requerido:
    {"puntaje": <numero entero exacto de la tarjeta elegida>}
    """
    
    payload = {
        "model": "llava",
        "prompt": prompt,
        "images": [base64_respuesta, base64_panel],
        "stream": False,
        "format": "json",
        "keep_alive": 0  # <--- MAGIA: Obliga a Ollama a descargar la memoria de la tarjeta gráfica
    }
    
    for intento in range(2):
        try:
            respuesta = requests.post("http://localhost:11434/api/generate", json=payload)
            respuesta.raise_for_status()
            diccionario_nota = json.loads(respuesta.json()["response"])
            print(f"✅ Evaluación completada: {diccionario_nota}")
            return diccionario_nota
        except Exception as e:
            print(f"⚠️ Servidor ocupado (Intento {intento+1}/2).")
            time.sleep(3)
    return {"puntaje": 0}