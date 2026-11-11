"""Normalización de texto: minúsculas, sin tildes ni emojis, abreviaturas de chat y errores de tipeo.

Nada de acá depende del tema de los datos: son reglas generales del castellano escrito en redes.
"""
import re
import unicodedata
from collections import Counter

ABREVIATURAS = {"q": "que", "k": "que", "xq": "porque", "pq": "porque", "x": "por", "pa": "para",
                "tmb": "tambien", "tb": "tambien", "tdo": "todo", "d": "de"}
PALABRAS_VACIAS = frozenset("""a al algo ante con como de del desde el ella ellos en entre es esa ese eso esta
este esto fue ha han hay la las le les lo los mas me mi muy nos o para pero por que se si sin sobre son su sus
te un una uno unos y ya ahi aca""".split())

_RE_URL = re.compile(r"https?://\S+|www\.\S+")
_RE_MENCION = re.compile(r"@\w[\w.]*")
_RE_NO_ALFANUM = re.compile(r"[^a-zñ0-9\s]")
_RE_REPETIDA = re.compile(r"([a-zñ])\1{2,}")


def normalizar(texto: str) -> str:
    t = _RE_URL.sub(" enlace ", texto.lower())
    t = _RE_MENCION.sub(" mencion ", t).replace("ñ", "\x00")
    t = "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn").replace("\x00", "ñ")
    t = _RE_REPETIDA.sub(r"\1", _RE_NO_ALFANUM.sub(" ", t))
    return " ".join(ABREVIATURAS.get(p, p) for p in t.split())


def _candidatas(palabra: str):
    """Variantes a un error de tipeo de distancia: letras vecinas invertidas o una letra duplicada de más."""
    for i in range(len(palabra) - 1):
        if palabra[i] != palabra[i + 1]:
            yield palabra[:i] + palabra[i + 1] + palabra[i] + palabra[i + 2:]
        else:
            yield palabra[:i] + palabra[i + 1:]


def corregir_tipeo(textos: list, pesos: list, min_largo: int = 4, razon: int = 10) -> list:
    """Reemplaza palabras raras por una palabra mucho más frecuente del mismo set que está a un error de tipeo."""
    frec = Counter()
    for t, n in zip(textos, pesos):
        for p in t.split():
            frec[p] += n
    cambio = {}
    for p, n in frec.items():
        if len(p) < min_largo or p.isdigit():
            continue
        mejor = max(_candidatas(p), key=lambda c: (frec.get(c, 0), c), default=None)
        if mejor is not None and frec.get(mejor, 0) >= razon * n:
            cambio[p] = mejor
    if not cambio:
        return textos
    return [" ".join(cambio.get(p, p) for p in t.split()) for t in textos]
