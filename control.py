import pyautogui
import pytesseract
import time
import mss
from PIL import Image

pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

def abrir_rubrica_en_respuesta(x, y):
    print(f"🖱️ Desplegando menú central en (X:{x}, Y:{y})...")
    pyautogui.moveTo(x, y, duration=0.2)
    pyautogui.click()
    time.sleep(2)

def fotografiar_acordeon(id_subpregunta):
    """FASE 1: Abre el inciso y toma una foto ajustada solo al panel."""
    print(f"\n📸 Preparando fotografía del inciso '{id_subpregunta}'...")
    with mss.mss() as sct:
        img = Image.frombytes("RGB", sct.grab(sct.monitors[1]).size, sct.grab(sct.monitors[1]).bgra, "raw", "BGRX")
    
    datos_ocr = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
    for i in range(len(datos_ocr['text'])):
        if id_subpregunta.lower() in datos_ocr['text'][i].lower():
            x = datos_ocr['left'][i] + (datos_ocr['width'][i] // 2)
            y = datos_ocr['top'][i] + (datos_ocr['height'][i] // 2)
            pyautogui.moveTo(x, y, duration=0.2)
            pyautogui.click()
            time.sleep(1.5)
            break
            
    # Recorte inteligente: Solo toma el 30% derecho de la pantalla
    ancho, alto = pyautogui.size()
    ancho_panel = int(ancho * 0.30)
    region_panel = {"top": 0, "left": ancho - ancho_panel, "width": ancho_panel, "height": alto}
    
    with mss.mss() as sct:
        img_panel = Image.frombytes("RGB", sct.grab(region_panel).size, sct.grab(region_panel).bgra, "raw", "BGRX")
        
    ruta_panel = f"panel_{id_subpregunta}.jpg"
    img_panel.save(ruta_panel)
    return ruta_panel

def ingresar_evaluacion(id_subpregunta, puntaje):
    """FASE 3: Abre el inciso y hace clic en los puntos calculados."""
    print(f"\n🖱️ FASE DE ACCIÓN: Ingresando {puntaje} pts a '{id_subpregunta}'")
    
    # 1. Volver a abrir el inciso (porque evaluar otro lo pudo haber cerrado)
    with mss.mss() as sct:
        img = Image.frombytes("RGB", sct.grab(sct.monitors[1]).size, sct.grab(sct.monitors[1]).bgra, "raw", "BGRX")
    datos_ocr = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
    
    for i in range(len(datos_ocr['text'])):
        if id_subpregunta.lower() in datos_ocr['text'][i].lower():
            x = datos_ocr['left'][i] + (datos_ocr['width'][i] // 2)
            y = datos_ocr['top'][i] + (datos_ocr['height'][i] // 2)
            pyautogui.moveTo(x, y, duration=0.2)
            pyautogui.click()
            time.sleep(1.5)
            break

    # 2. Buscar y hacer clic en los puntos
    clic_exitoso = False
    for intento in range(3):
        with mss.mss() as sct:
            img_pts = Image.frombytes("RGB", sct.grab(sct.monitors[1]).size, sct.grab(sct.monitors[1]).bgra, "raw", "BGRX")
        datos_pts = pytesseract.image_to_data(img_pts, output_type=pytesseract.Output.DICT)
        
        for i in range(len(datos_pts['text']) - 1):
            if str(puntaje) == datos_pts['text'][i].strip().lower() and "pts" in datos_pts['text'][i+1].strip().lower():
                x_pts = datos_pts['left'][i] + (datos_pts['width'][i] // 2)
                y_pts = datos_pts['top'][i] - 25 
                pyautogui.moveTo(x_pts, y_pts, duration=0.2)
                pyautogui.click()
                print(f"✅ Clic en {puntaje} pts realizado.")
                clic_exitoso = True
                break
                
        if clic_exitoso: break
        pyautogui.scroll(-300)
        time.sleep(1)
    
    time.sleep(1)

def guardar_nota_pregunta():
    print("💾 Buscando botón azul 'Guardar'...")
    time.sleep(1)
    try:
        btn_x, btn_y = pyautogui.locateCenterOnScreen('btn_guardar_azul.png', confidence=0.8)
        pyautogui.moveTo(btn_x, btn_y, duration=0.2)
        pyautogui.click()
        print("✅ Guardado exitosamente.")
        time.sleep(2)
        return True
    except Exception as e:
        print(f"❌ Error visual al guardar: No se encontró el botón azul.")
        return False

def avanzar_siguiente_alumno(coords_siguiente):
    print("⏭️ Pasando al Siguiente Alumno...")
    pyautogui.moveTo(coords_siguiente["x"], coords_siguiente["y"], duration=0.2)
    pyautogui.click()
    time.sleep(4)