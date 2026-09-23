import pyautogui
import time
import sys

def rastrear_mouse():
    print("=== Calibrador de Pantalla para Emarking ===")
    print("Instrucciones:")
    print("1. Maximiza la ventana de tu navegador con WebC.")
    print("2. Mueve el mouse a los puntos clave (esquinas de los paneles, botones).")
    print("3. Anota los valores X e Y que aparecen abajo.")
    print("4. Presiona Ctrl + C en esta terminal para detener el programa.\n")
    
    try:
        while True:
            x, y = pyautogui.position()
            # \r hace que el texto reescriba la misma línea constantemente
            sys.stdout.write(f"\rCoordenadas actuales -> X: {x:4d} | Y: {y:4d}")
            sys.stdout.flush()
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\n\nCalibración finalizada. Ingresa estos números en tu config.json.")

if __name__ == "__main__":
    rastrear_mouse()
    