"""Lectura de la pauta PDF: enunciado, solución y niveles de logro de cada inciso."""
import re

import pymupdf

# LaTeX exporta los acentos como carácter suelto + letra ("l´ogicas" -> "lógicas").
_ACENTOS = {"a": "á", "e": "é", "i": "í", "ı": "í", "o": "ó", "u": "ú",
            "A": "Á", "E": "É", "I": "Í", "O": "Ó", "U": "Ú"}


def _normalizar(texto):
    texto = re.sub(r"´\s?([aeiouAEIOUı])", lambda m: _ACENTOS[m.group(1)], texto)
    texto = re.sub(r"˜\s?n", "ñ", texto)
    texto = re.sub(r"˜\s?N", "Ñ", texto)
    texto = re.sub(r"¨\s?u", "ü", texto)
    return texto


def _compactar(texto):
    return re.sub(r"[ \t]*\n[ \t]*", "\n", texto).strip()


def _cortar_secuencial(texto, patron, primero, siguiente):
    """Corta el texto en los inicios que calzan con `patron` siempre que el identificador
    sea el esperado (1, 2, 3... o a, b, c...). Evita cortar en listas internas de la solución."""
    cortes = []
    esperado = primero
    for m in re.finditer(patron, texto):
        if m.group(1) == esperado:
            cortes.append((m.group(1), m.start(), m.end()))
            esperado = siguiente(esperado)
    bloques = []
    for i, (ident, inicio, fin_encabezado) in enumerate(cortes):
        fin = cortes[i + 1][1] if i + 1 < len(cortes) else len(texto)
        bloques.append((ident, texto[fin_encabezado:fin], inicio))
    return bloques


_PATRON_NIVEL = re.compile(
    r"Nivel\s+(\d+)\s+(\d+(?:[.,]\d+)?)\s*(?:ptos?|pts?|puntos?)\.?\s+(.*?)(?=\s*Nivel\s+\d+\s+\d|\Z)",
    re.S | re.I,
)


def _parsear_inciso(id_inciso, cuerpo, contexto):
    partes = re.split(r"Niveles de logro[^\n]*", cuerpo, maxsplit=1, flags=re.I)
    antes_rubrica = partes[0]
    rubrica = partes[1] if len(partes) > 1 else ""

    sol = re.split(r"Soluci[oó]n\.?", antes_rubrica, maxsplit=1, flags=re.I)
    enunciado = _compactar(sol[0])
    solucion = _compactar(sol[1]) if len(sol) > 1 else ""

    niveles = []
    for m in _PATRON_NIVEL.finditer(rubrica):
        puntos = float(m.group(2).replace(",", "."))
        niveles.append({
            "nivel": int(m.group(1)),
            "puntos": int(puntos) if puntos.is_integer() else puntos,
            "descripcion": re.sub(r"\s+", " ", m.group(3)).strip(),
        })

    return {
        "id": id_inciso,
        "contexto": contexto,
        "enunciado": enunciado,
        "solucion": solucion,
        "niveles": niveles,
        "puntaje_max": max((n["puntos"] for n in niveles), default=None),
    }


def procesar_pauta_pdf(ruta_pdf):
    """Devuelve {"1": {"numero", "contexto", "incisos": {"1a": {...}, "1b": {...}}}, "2": {...}, ...}.
    Si la pregunta no tiene incisos a), b)... se crea un único inciso con el número ("3")."""
    print(f"📄 Abriendo pauta de evaluación: {ruta_pdf}")
    try:
        with pymupdf.open(ruta_pdf) as pdf:
            texto = "\n".join(pagina.get_text() for pagina in pdf)
    except Exception as e:
        print(f"❌ Error al leer el PDF: {e}")
        return {}

    texto = _normalizar(texto)
    preguntas = {}
    bloques = _cortar_secuencial(texto, r"(?m)^\s*(\d{1,2})\.\s+", "1", lambda n: str(int(n) + 1))
    for numero, cuerpo, _ in bloques:
        sub = _cortar_secuencial(cuerpo, r"(?m)^\s*([a-z])\)\s+", "a", lambda c: chr(ord(c) + 1))
        if sub:
            contexto = _compactar(cuerpo[:sub[0][2]])
            incisos = {f"{numero}{letra}": _parsear_inciso(f"{numero}{letra}", c, contexto) for letra, c, _ in sub}
        else:
            incisos = {numero: _parsear_inciso(numero, cuerpo, "")}
        preguntas[numero] = {"numero": numero, "incisos": incisos}

    total = sum(len(p["incisos"]) for p in preguntas.values())
    print(f"✅ Pauta cargada: {len(preguntas)} preguntas, {total} incisos.")
    return preguntas


def buscar_inciso(pauta, id_inciso):
    """Busca un inciso tolerando formatos como '1a', '1 a', '1a)', '3'."""
    clave = re.sub(r"[^0-9a-z]", "", id_inciso.lower())
    for pregunta in pauta.values():
        if clave in pregunta["incisos"]:
            return pregunta["incisos"][clave]
    return None
