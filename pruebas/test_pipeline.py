"""Pruebas mínimas del pipeline: formato de salida, datos sucios o faltantes y reproducibilidad.

    python -m unittest discover -s pruebas -v
"""
import csv
import gzip
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from pipeline.run import correr
from pipeline.validar import validar_entrega
from pipeline.texto import corregir_tipeo, normalizar

RAIZ = Path(__file__).resolve().parent.parent
PRACTICA = RAIZ / "datos" / "practica"
COLUMNAS = ["comentario_id", "publicacion_id", "cuenta_id", "fecha", "texto", "respuesta_a", "me_gusta"]


def leer(ruta: Path) -> list:
    with open(ruta, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def escribir(ruta: Path, columnas: list, filas: list):
    abrir = gzip.open if ruta.suffix == ".gz" else open
    with abrir(ruta, "wt", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(columnas)
        w.writerows(filas)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="qualydata_"))
        self.datos, self.entrega = self.tmp / "datos", self.tmp / "entrega"
        self.datos.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def correr(self, entrega=None):
        entrega = entrega or self.entrega
        correr(self.datos, entrega, self.tmp / f"{entrega.name}.duckdb", reporte=self.tmp / f"{entrega.name}.html")
        html = (self.tmp / f"{entrega.name}.html").read_text(encoding="utf-8")
        self.assertIn("Qué circula, desde cuándo y quién lo empuja", html)
        self.assertNotIn("http://", html)   # archivo estático: sin recursos externos
        self.assertNotIn("https://", html)
        return entrega

    def revisar_formato(self, entrega: Path, ids_comentarios: set, ids_cuentas: set):
        comentarios, narrativas, cuentas = (leer(entrega / f"{n}.csv") for n in ("comentarios", "narrativas", "cuentas"))
        self.assertEqual({c["comentario_id"] for c in comentarios}, ids_comentarios)
        self.assertEqual(len(comentarios), len(ids_comentarios))
        self.assertEqual({c["cuenta_id"] for c in cuentas}, ids_cuentas)
        etiquetas = {n["narrativa"] for n in narrativas}
        for c in comentarios:
            if c["narrativa"] in ("", "ninguna"):
                self.assertEqual(c["postura"], "")
            else:
                self.assertIn(c["narrativa"], etiquetas)
                self.assertIn(c["postura"], ("apoya", "rechaza"))
        for n in narrativas:
            self.assertRegex(n["fecha_origen"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$")
        errores, _avisos, _resumen = validar_entrega(entrega, self.datos)
        self.assertEqual(errores, [])
        costo = json.loads((entrega / "costo.json").read_text(encoding="utf-8"))
        for clave in ("comentarios_procesados", "segundos", "tokens_ia", "usd_ia", "usd_por_mil_comentarios",
                      "hardware", "almacenamiento", "notas"):
            self.assertIn(clave, costo)
        self.assertEqual(costo["comentarios_procesados"], len(ids_comentarios))


class TextoTest(unittest.TestCase):
    def test_normalizar(self):
        self.assertEqual(normalizar("¡¡Qué BRONCAAA!! 😡 xq no @juan.perez https://x.y/z"), "que bronca porque no mencion enlace")
        self.assertEqual(normalizar("El año del ñandú"), "el año del ñandu")
        self.assertEqual(normalizar("👀"), "")

    def test_corregir_tipeo(self):
        textos = ["el problema del agua"] * 20 + ["el prbolema del aguaa"]
        self.assertEqual(corregir_tipeo(textos, [1] * 21)[-1], "el problema del agua")


class DatosChicosTest(Base):
    def test_set_minimo(self):
        filas = [["c1", "p1", "u1", "2026-09-01T10:00:00-03:00", "La obra está parada hace meses", "", "3"],
                 ["c2", "p1", "u2", "2026-09-01T10:05:00-03:00", "Tal cual", "c1", "0"],
                 ["c3", "p1", "u3", "2026-09-01T10:07:00-03:00", "Mentira, la obra avanza", "c1", "1"],
                 ["c4", "p1", "u2", "2026-09-01T10:09:00-03:00", "👏👏", "", "0"]]
        escribir(self.datos / "comentarios.csv", COLUMNAS, filas)
        self.revisar_formato(self.correr(), {"c1", "c2", "c3", "c4"}, {"u1", "u2", "u3"})

    def test_un_solo_comentario(self):
        escribir(self.datos / "comentarios.csv", COLUMNAS, [["c1", "p1", "u1", "2026-09-01T10:00:00-03:00", "Hola", "", "0"]])
        self.revisar_formato(self.correr(), {"c1"}, {"u1"})

    def test_faltan_columnas(self):
        escribir(self.datos / "comentarios.csv", ["comentario_id", "texto"],
                 [[f"c{i}", "La obra está parada hace meses y nadie explica nada"] for i in range(40)])
        self.revisar_formato(self.correr(), {f"c{i}" for i in range(40)}, set())

    def test_sin_ninguna_fecha_valida(self):
        filas = [[f"c{i}", "p1", f"u{i % 7}", "ayer", "La obra está parada hace meses y nadie explica nada", "", "0"] for i in range(60)]
        filas += [[f"r{i}", "p1", f"u{i % 5}", "", "Mentira, la obra avanza y ya retomaron los trabajos", f"c{i}", "x"] for i in range(60)]
        escribir(self.datos / "comentarios.csv", COLUMNAS, filas)
        self.revisar_formato(self.correr(), {f[0] for f in filas}, {f"u{i}" for i in range(7)})

    def test_hilos_raros_y_cuentas_vacias(self):
        filas = [["c1", "p1", "u1", "2026-09-01T10:00:00-03:00", "La obra está parada", "c2", "1"],   # ciclo c1 <-> c2
                 ["c2", "p1", "u2", "2026-09-01T10:01:00-03:00", "Mentira, la obra avanza", "c1", "1"],
                 ["c3", "p1", "u3", "2026-09-01T10:02:00-03:00", "Tal cual", "c3", "1"],              # se responde a sí mismo
                 ["c4", "p1", "", "2026-09-01T10:03:00-03:00", "Comentario sin cuenta", "c_no_existe", "-5"],
                 ["c5", "", "u1", "2026-09-01T10:04:00-03:00", 'Texto con "comillas", comas\ny salto de línea', "", ""]]
        escribir(self.datos / "comentarios.csv", COLUMNAS, filas)
        escribir(self.datos / "cuentas.csv", ["cuenta_id", "usuario", "fecha_creacion", "seguidores", "siguiendo"],
                 [["u1", "a", "2020-01-01", "10", "5"], ["u1", "a", "2020-01-01", "10", "5"], ["u9", "b", "no sé", "muchos", ""]])
        self.revisar_formato(self.correr(), {"c1", "c2", "c3", "c4", "c5"}, {"u1", "u2", "u3", "u9"})

    def test_bom_punto_y_coma_y_latin1(self):
        filas = [[f"c{i}", "p1", f"u{i % 9}", "2026-09-01T10:00:00-03:00", "La obra está parada hace más de un año", "", "0"] for i in range(30)]
        texto = "\n".join(";".join(f) for f in [COLUMNAS, *filas]) + "\n"
        for nombre, contenido in (("con_bom", "\ufeff".encode("utf-8") + texto.encode("utf-8")),
                                  ("latin1", texto.encode("latin-1"))):
            (self.datos / "comentarios.csv").write_bytes(contenido)
            entrega = self.correr(self.tmp / nombre)
            self.revisar_formato(entrega, {f[0] for f in filas}, {f"u{i}" for i in range(9)})
            self.assertIn("más de un año", (entrega / "narrativas.csv").read_text(encoding="utf-8"), nombre)

    def test_sin_comentarios(self):
        escribir(self.datos / "comentarios.csv.gz", COLUMNAS, [])
        self.revisar_formato(self.correr(), set(), set())

    def test_falta_el_archivo_de_comentarios(self):
        with self.assertRaises(FileNotFoundError):
            self.correr()


class ValidadorTest(Base):
    """El validador tiene que aceptar una entrega buena y señalar cada tipo de defecto."""

    def setUp(self):
        super().setUp()
        filas = [[f"c{i}", "p1", f"u{i % 9}", "2026-09-01T10:00:00-03:00", "La obra está parada hace más de un año", "", "0"] for i in range(30)]
        escribir(self.datos / "comentarios.csv", COLUMNAS, filas)
        self.correr()

    def errores(self):
        return validar_entrega(self.entrega, self.datos)[0]

    def reescribir(self, archivo, cambio):
        ruta = self.entrega / archivo
        ruta.write_text(cambio(ruta.read_text(encoding="utf-8")), encoding="utf-8", newline="")

    def test_entrega_buena(self):
        self.assertEqual(self.errores(), [])

    def test_falta_un_archivo(self):
        (self.entrega / "cuentas.csv").unlink()
        self.assertTrue(any("falta el archivo cuentas.csv" in e for e in self.errores()))

    def test_encabezado_distinto(self):
        self.reescribir("comentarios.csv", lambda t: t.replace("comentario_id,narrativa,postura", "id,narrativa,postura", 1))
        self.assertTrue(any("encabezado" in e for e in self.errores()))

    def test_postura_invalida(self):
        self.reescribir("comentarios.csv", lambda t: t.replace(",apoya", ",a favor", 1))
        self.assertTrue(any("postura" in e for e in self.errores()))

    def test_falta_un_comentario_y_hay_un_repetido(self):
        self.reescribir("comentarios.csv", lambda t: t.replace("c7,", "c8,", 1))
        errores = " | ".join(self.errores())
        self.assertIn("repetidos", errores)
        self.assertIn("faltan 1 comentario_id", errores)

    def test_fecha_sin_zona_horaria(self):
        self.reescribir("narrativas.csv", lambda t: t.replace("-03:00", ""))
        self.assertTrue(any("fecha_origen" in e for e in self.errores()))

    def test_narrativa_sin_fila(self):
        self.reescribir("comentarios.csv", lambda t: t.replace("n01,", "n99,", 1))
        self.assertTrue(any("narrativas usadas" in e for e in self.errores()))

    def test_costo_incompleto(self):
        def romper(texto):
            costo = json.loads(texto)
            del costo["tokens_ia"]
            costo["segundos"] = "rápido"
            return json.dumps(costo, ensure_ascii=False)

        self.reescribir("costo.json", romper)
        errores = " | ".join(self.errores())
        self.assertIn("falta la clave tokens_ia", errores)
        self.assertIn("segundos debe ser un número", errores)


@unittest.skipUnless((PRACTICA / "comentarios.csv.gz").exists(), "no está el set de práctica")
class MuestraPracticaTest(Base):
    N = 30000

    def armar(self, ensuciar: bool):
        with gzip.open(PRACTICA / "comentarios.csv.gz", "rt", encoding="utf-8", newline="") as f:
            filas = [fila for _, fila in zip(range(self.N + 1), csv.reader(f))][1:]
        if ensuciar:
            for i, fila in enumerate(filas):
                if i % 97 == 0:
                    fila[3] = "ayer a la tarde"        # fecha imposible
                if i % 101 == 0:
                    fila[6] = "muchos"                 # me_gusta no numérico
                if i % 103 == 0:
                    fila[4] = ""                       # texto vacío
                if i % 107 == 0:
                    fila[5] = "c_no_existe"            # responde a un comentario que no está
            filas += filas[:500]                       # duplicados exactos
            filas.append(["", "p00001", "u000001", "2026-09-01T10:00:00-03:00", "sin id", "", "0"])
            escribir(self.datos / "comentarios.csv", COLUMNAS[:-1], [f[:-1] for f in filas])  # sin columna me_gusta
        else:
            escribir(self.datos / "comentarios.csv.gz", COLUMNAS, filas)
            shutil.copy(PRACTICA / "cuentas.csv.gz", self.datos / "cuentas.csv.gz")
            shutil.copy(PRACTICA / "publicaciones.csv.gz", self.datos / "publicaciones.csv.gz")
        return {f[0] for f in filas if f[0]}, {f[2] for f in filas if f[0]}

    def test_datos_sucios_y_archivos_faltantes(self):
        ids, cuentas = self.armar(ensuciar=True)
        self.revisar_formato(self.correr(), ids, cuentas)

    def test_dos_corridas_dan_lo_mismo(self):
        self.armar(ensuciar=False)
        primera, segunda = self.correr(self.tmp / "a"), self.correr(self.tmp / "b")
        for archivo in ("comentarios.csv", "narrativas.csv", "cuentas.csv"):
            self.assertEqual((primera / archivo).read_bytes(), (segunda / archivo).read_bytes(), archivo)
        con_narrativa = sum(1 for c in leer(primera / "comentarios.csv") if c["narrativa"] not in ("", "ninguna"))
        self.assertGreater(con_narrativa, self.N // 2)
        html = (self.tmp / "a.html").read_text(encoding="utf-8")
        self.assertIn("1 · Narrativas", html)
        self.assertIn("<svg", html)


if __name__ == "__main__":
    unittest.main()
