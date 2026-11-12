"""Único comando del pipeline, de punta a punta:

    python -m pipeline.run --datos datos/practica --entrega salida/practica
    python -m pipeline.run --datos datos/final --entrega entrega

Lee los CSV de --datos, los guarda en una base DuckDB local (--base) y escribe en --entrega
comentarios.csv, narrativas.csv, cuentas.csv y costo.json. Al final valida el formato de la entrega
(pipeline/validar.py), termina con error si no cumple, y genera un reporte visual en reporte/<entrega>.html.
No usa IA ni servicios externos.
"""
import argparse
import json
import sys
import time
import traceback
from pathlib import Path

import numpy as np

from .consignas import reubicar_consignas
from .coordinacion import detectar_coordinacion
from .costo import armar_costo, memoria_mb
from .ingesta import ingerir
from .narrativas import detectar_narrativas
from .parametros import de_etapa, interpretar, resolver
from .postura import calcular_bandos, orientar, postura_por_comentario
from .reporte import generar_reporte
from .salida import describir_narrativas, escribir_costo, escribir_entrega
from .validar import EntregaInvalida, informe, validar_entrega


class Reloj:
    """Mide segundos y memoria de cada etapa."""

    def __init__(self):
        self.etapas = {}
        self.inicio = time.perf_counter()

    def etapa(self, nombre, funcion, *args, **kwargs):
        t0 = time.perf_counter()
        resultado = funcion(*args, **kwargs)
        memoria, pico = memoria_mb()
        self.etapas[nombre] = {"segundos": round(time.perf_counter() - t0, 2), "memoria_mb": memoria, "pico_mb": pico}
        print(f"[{nombre}] {self.etapas[nombre]['segundos']} s, memoria {memoria} MB (pico {pico} MB)", flush=True)
        return resultado


def _a_float(columna) -> np.ndarray:
    """Columna numérica de DuckDB a float, con NaN donde había NULL."""
    if np.ma.isMaskedArray(columna):
        return np.ma.filled(columna.astype(np.float64), np.nan)
    return np.asarray(columna, dtype=np.float64)


def correr(datos: Path, entrega: Path, base: Path, semilla: int = 0, hardware: str = None, reporte: Path = None,
           parametros: dict = None) -> dict:
    """`parametros` cambia valores de parametros.py solo para esta corrida (queda anotado en costo.json)."""
    p = resolver(parametros)
    reloj = Reloj()
    np.random.seed(semilla)
    con, resumen = reloj.etapa("ingesta", ingerir, datos, base)
    print(f"  {resumen['comentarios']} comentarios, {resumen['textos_unicos']} textos únicos, "
          f"{resumen['cuentas']} cuentas, {resumen['respuestas']} respuestas", flush=True)

    com = con.execute("SELECT texto_id, padre, pub, cuenta, ts, hora_local, me_gusta FROM comentarios ORDER BY i").fetchnumpy()
    texto_id, padre = com["texto_id"].astype(np.int64), com["padre"].astype(np.int64)
    ts = _a_float(com["ts"])
    tx = con.execute("SELECT texto, n FROM textos ORDER BY texto_id").fetchnumpy()
    textos, n_textos = list(tx["texto"]), tx["n"].astype(np.int64)
    cuentas = con.execute("SELECT creada_ts, seguidores, siguiendo FROM cuentas ORDER BY cuenta").fetchnumpy()

    nar = reloj.etapa("narrativas", detectar_narrativas, textos, n_textos, texto_id, padre, semilla=semilla,
                      **de_etapa(p, "narrativas"))
    print(f"  {json.dumps(nar.info, ensure_ascii=False)}", flush=True)

    avisos = list(resumen["avisos"])
    if not nar.info["usa_hilos"] and resumen["comentarios"]:
        avisos.append("ALERTA: el set casi no trae respuestas (respuesta_a), así que no se pudo usar la conversación: "
                      "narrativas, ruido y postura salen del plan B por palabras, que es mucho menos confiable")
        print(f"  {avisos[-1]}", flush=True)
    n_cuentas = len(cuentas["seguidores"])
    n_com = int(nar.comunidad.max()) + 1 if len(nar.comunidad) else 0
    cuenta = com["cuenta"].astype(np.int64)

    def etapa_bandos():
        bando = calcular_bandos(nar)
        return bando, postura_por_comentario(nar, bando, np.ones(n_com), padre)

    try:
        bando, bando_com = reloj.etapa("bandos", etapa_bandos)
    except Exception:
        traceback.print_exc()
        avisos.append("falló el armado de bandos: se asignó 'apoya' a todo")
        bando, bando_com = np.ones(len(nar.tipo)), (nar.narrativa >= 0).astype(float)

    try:
        grupo_cuenta, info_coord = reloj.etapa(
            "coordinacion", detectar_coordinacion, n_cuentas=n_cuentas, cuenta=cuenta,
            pub=com["pub"].astype(np.int64), ts=ts, narrativa=nar.narrativa, bando=bando_com,
            creada_ts=_a_float(cuentas["creada_ts"]), usar_mensaje=nar.info["usa_hilos"], micro=nar.micro,
            **de_etapa(p, "coordinacion"))
    except Exception:  # la entrega sale igual, sin grupos
        traceback.print_exc()
        avisos.append("falló la etapa de coordinación: no se marcaron cuentas")
        grupo_cuenta, info_coord = np.full(n_cuentas, "", dtype=object), {"error": True}
    print(f"  {json.dumps(info_coord, ensure_ascii=False)}", flush=True)
    tope = info_coord.get("tope", {})
    if tope.get("activado"):
        pasos = ", ".join(f"{x['umbral']} {x['antes']:g} -> {x['despues']:g} ({x['cuentas_marcadas']} cuentas)" for x in tope["pasos"])
        avisos.append(
            f"ALERTA: tope de seguridad de coordinación activado. Con los umbrales normales se marcaban {tope['marcadas_inicial']} "
            f"cuentas (más del {100 * tope['tope_fraccion']:g}% del set), así que se endurecieron solos: {pasos}. "
            + ("Quedó por debajo del tope" if tope["bajo_el_tope"] else "NO se logró bajar del tope: revisar la coordinación a mano"))
        print(f"  {avisos[-1]}", flush=True)

    if p["reubicar_consignas"] and nar.info["usa_hilos"] and (grupo_cuenta != "").any():
        try:
            bando, info_consignas = reloj.etapa("consignas", reubicar_consignas, nar, bando, grupo_cuenta, cuenta, padre,
                                                umbral_parecido=p["umbral_parecido"])
            print(f"  {json.dumps(info_consignas, ensure_ascii=False)}", flush=True)
        except Exception:
            traceback.print_exc()
            avisos.append("falló la reubicación de consignas: quedaron donde las dejó la conversación")

    def etapa_postura():
        coordinado = (grupo_cuenta != "")[cuenta] if n_cuentas else None
        signo, detalle = orientar(nar, bando, texto_id, padre, coordinado, **de_etapa(p, "postura"))
        return signo, postura_por_comentario(nar, bando, signo, padre), detalle

    try:
        signo, postura, detalle_postura = reloj.etapa("postura", etapa_postura)
    except Exception:
        traceback.print_exc()
        avisos.append("falló la orientación de la postura: quedó el bando sin orientar")
        signo, postura, detalle_postura = np.ones(n_com), bando_com, {}

    etiquetas, filas = reloj.etapa("origen_y_titulos", describir_narrativas, nar, bando, signo, textos, n_textos,
                                   ts, resumen["zona_seg"], **de_etapa(p, "origen"))
    for f in filas:
        print(f"  {f['narrativa']} {f['comentarios']:>6} {f['fecha_origen']}  {f['titulo'][:70]}", flush=True)
    comunidad_de = {etiqueta: c for c, etiqueta in enumerate(etiquetas.tolist()) if etiqueta}
    for f in filas:  # cuánta evidencia hubo para decidir qué bando apoya (lo muestra el reporte)
        d = detalle_postura.get(comunidad_de.get(f["narrativa"]), {})
        partes = {k: v for k, v in d.items() if k not in ("puntaje", "motivo")}
        a_favor = {k: abs(v) for k, v in partes.items() if v * d.get("puntaje", 0) > 0}
        f["puntaje_postura"] = abs(float(d.get("puntaje", 0.0)))
        f["indicio_postura"] = d.get("motivo") or (max(a_favor, key=a_favor.get) if a_favor else "")
    sin_fecha = sum(f["sin_fecha"] for f in filas)
    if sin_fecha:
        avisos.append(f"{sin_fecha} narrativas sin ninguna fecha válida: su fecha_origen es la primera fecha del set")
    if resumen["comentarios_sin_fecha"]:
        avisos.append(f"{resumen['comentarios_sin_fecha']} comentarios sin fecha válida (no se usan para origen ni coordinación)")
    if resumen["comentarios_descartados"]:
        avisos.append(f"{resumen['comentarios_descartados']} filas de comentarios descartadas (id vacío o repetido)")
    reloj.etapa("escritura", escribir_entrega, con, entrega, etiquetas, nar.narrativa, postura, filas, grupo_cuenta)
    con.close()

    def guardar_costo():
        costo = armar_costo(resumen["comentarios"], time.perf_counter() - reloj.inicio, reloj.etapas, resumen["archivos"],
                            base, entrega, avisos, semilla, hardware)
        costo["parametros_cambiados"] = dict(parametros or {})
        costo["tope_coordinacion"] = tope
        escribir_costo(entrega, costo)
        return costo

    # Control final: los 4 archivos con el formato exacto del enunciado y los mismos ids que la entrada.
    guardar_costo()
    errores, avisos_formato, resumen_formato = reloj.etapa("validacion", validar_entrega, entrega, datos)
    print(informe(entrega, errores, avisos_formato, resumen_formato), flush=True)
    if reporte is not None and not errores:
        try:  # extra aislado: si falla, la entrega ya está escrita y validada
            ruta = reloj.etapa("reporte", generar_reporte, base, reporte, guardar_costo(), Path(datos).resolve().name)
            print(f"Reporte visual en {ruta}", flush=True)
        except Exception:
            traceback.print_exc()
            print("No se pudo generar el reporte visual (la entrega no se ve afectada).", flush=True)
    costo = guardar_costo()  # se reescribe con el tiempo total, validación y reporte incluidos
    print(f"Listo en {costo['segundos']} s, memoria pico {costo['memoria_pico_mb']} MB. Entrega en {entrega}/", flush=True)
    if errores:
        raise EntregaInvalida(f"la entrega en {entrega} no cumple el formato: {errores[0]}")
    return costo


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--datos", type=Path, required=True, help="Carpeta con comentarios/cuentas/publicaciones/fuentes (.csv o .csv.gz)")
    ap.add_argument("--entrega", type=Path, required=True, help="Carpeta donde se escriben los 4 archivos")
    ap.add_argument("--base", type=Path, default=None, help="Archivo DuckDB (por defecto almacen/<nombre de --datos>.duckdb)")
    ap.add_argument("--semilla", type=int, default=0)
    ap.add_argument("--hardware", default=None, help="Texto para costo.json si no se quiere el equipo detectado solo")
    ap.add_argument("--reporte", type=Path, default=None,
                    help="Archivo HTML del reporte visual (por defecto reporte/<nombre de --entrega>.html)")
    ap.add_argument("--sin-reporte", action="store_true", help="No generar el reporte visual")
    ap.add_argument("--param", action="append", default=[], metavar="NOMBRE=VALOR",
                    help="Cambia un parámetro de pipeline/parametros.py solo para esta corrida (se puede repetir)")
    args = ap.parse_args(argv)
    base = args.base or Path("almacen") / f"{args.datos.resolve().name}.duckdb"
    for flujo in (sys.stdout, sys.stderr):
        if hasattr(flujo, "reconfigure"):
            flujo.reconfigure(encoding="utf-8", errors="replace")
    try:
        reporte = None if args.sin_reporte else args.reporte or Path("reporte") / f"{args.entrega.resolve().name}.html"
        correr(args.datos, args.entrega, base, args.semilla, args.hardware, reporte, dict(interpretar(x) for x in args.param))
    except (FileNotFoundError, ValueError) as e:
        sys.exit(f"ERROR: {e}")
    except EntregaInvalida as e:
        sys.exit(f"ERROR: {e}")


if __name__ == "__main__":
    main()
