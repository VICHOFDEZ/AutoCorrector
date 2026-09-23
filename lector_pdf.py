import pymupdf as fitz
import re

def procesar_pauta_pdf(ruta_pdf):
    print(f"Abriendo pauta de evaluación: {ruta_pdf}")
    texto_completo = "\n" 
    try:
        with fitz.open(ruta_pdf) as pdf:
            for pagina in pdf:
                texto_completo += pagina.get_text() + "\n"
    except Exception as e:
        print(f"❌ Error al leer el PDF: {e}")
        return []

    patron = r"\n\s*(\d+)\.\s"
    fragmentos = re.split(patron, texto_completo)
    preguntas_estructuradas = []
    
    for i in range(1, len(fragmentos), 2):
        numero = fragmentos[i]
        pauta_texto = fragmentos[i+1].strip()
        id_pregunta = f"{numero}."
        
        if i + 2 < len(fragmentos):
            marcador_fin = f"{fragmentos[i+2]}."
        else:
            marcador_fin = "Fin de la prueba"
            
        preguntas_estructuradas.append({
            "id_pregunta": id_pregunta,
            "pauta": pauta_texto,
            "marcador_fin": marcador_fin
        })
        
    print(f"✅ Sistema memorizó {len(preguntas_estructuradas)} preguntas.")
    return preguntas_estructuradas