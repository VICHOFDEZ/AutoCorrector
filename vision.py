import mss
import mss.tools
import pyautogui
import pytesseract
import time
from PIL import Image
import re

pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

def capturar_region(coordenadas):
    with mss.mss() as sct:
        region = {
            "top": coordenadas["top_left_y"],
            "left": coordenadas["top_left_x"],
            "width": coordenadas["bottom_right_x"] - coordenadas["top_left_x"],
            "height": coordenadas["bottom_right_y"] - coordenadas["top_left_y"]
        }
        sct_img = sct.grab(region)
        return Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")

def buscar_inicio_pregunta(coords_visor, id_pregunta, max_scrolls=15):
    print(f"🔍 Buscando '{id_pregunta}' en el papel del alumno...")
    centro_x = coords_visor["top_left_x"] + (coords_visor["bottom_right_x"] - coords_visor["top_left_x"]) // 2
    centro_y = coords_visor["top_left_y"] + (coords_visor["bottom_right_y"] - coords_visor["top_left_y"]) // 2
    pyautogui.moveTo(centro_x, centro_y)
    
    match_numero = re.search(r'\d+', id_pregunta)
    numero_buscar = match_numero.group() if match_numero else id_pregunta
    
    for intento in range(max_scrolls):
        img_actual = capturar_region(coords_visor)
        datos_ocr = pytesseract.image_to_data(img_actual, output_type=pytesseract.Output.DICT)
        
        for i in range(len(datos_ocr['text'])):
            texto_palabra = datos_ocr['text'][i].lower()
            if re.search(rf"^{numero_buscar}[\.,]?$", texto_palabra):
                print(f"🎯 ¡'{id_pregunta}' encontrada en pantalla!")
                x_absoluto = coords_visor["top_left_x"] + datos_ocr['left'][i] + (datos_ocr['width'][i] // 2)
                y_absoluto = coords_visor["top_left_y"] + datos_ocr['top'][i] + (datos_ocr['height'][i] // 2)
                return True, x_absoluto, y_absoluto
                
        pyautogui.scroll(-800) 
        time.sleep(1.5)
        
    print(f"❌ No se encontró '{id_pregunta}'.")
    return False, 0, 0

def escanear_respuesta_completa(coords_visor, marcador_fin, max_scrolls=6):
    print(f"📸 Escaneando hasta ver '{marcador_fin}'...")
    imagenes_capturadas = []
    
    for intento in range(max_scrolls):
        img_actual = capturar_region(coords_visor)
        imagenes_capturadas.append(img_actual)
        texto_leido = pytesseract.image_to_string(img_actual).lower()
        texto_leido = re.sub(r'\s+', ' ', texto_leido)
        match_numero = re.search(r'\d+', marcador_fin)
        
        encontrado = False
        if match_numero:
            numero = match_numero.group()
            if re.search(rf"\b{numero}\s*[\.,]", texto_leido):
                encontrado = True
        elif marcador_fin.lower() in texto_leido:
            encontrado = True
            
        if marcador_fin != "Fin de la prueba" and encontrado:
            print(f"🛑 Marcador final '{marcador_fin}' detectado.")
            break
            
        pyautogui.scroll(-500) 
        time.sleep(1.5)

    ancho = imagenes_capturadas[0].width
    alto_total = sum(img.height for img in imagenes_capturadas)
    imagen_ensamblada = Image.new('RGB', (ancho, alto_total))
    
    y_offset = 0
    for img in imagenes_capturadas:
        imagen_ensamblada.paste(img, (0, y_offset))
        y_offset += img.height
        
    ruta_salida = "respuesta_temp.jpg"
    imagen_ensamblada.save(ruta_salida)
    print(f"✅ Captura ensamblada en {ruta_salida}")
    return ruta_salida