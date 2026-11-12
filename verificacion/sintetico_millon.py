"""Prueba SINTÉTICA de volumen: el set de práctica repetido hasta un millón de comentarios.

    python verificacion/sintetico_millon.py               # 5 copias = 1.000.000 de comentarios, tope de 15 minutos
    python verificacion/sintetico_millon.py --copias 2    # prueba chica del propio script (400.000)
    python verificacion/sintetico_millon.py --tabla       # imprime lo ya corrido

No son datos nuevos. Cada copia repite los 200.000 comentarios de práctica con otros ids de comentario, cuenta y
publicación, y con las fechas corridas un período entero (la copia 2 empieza donde termina la 1). Los textos son los
mismos, así que la prueba mide volumen (ingesta, hilos, cruce de cuentas, escritura y validación) y NO variedad de
texto: un millón de comentarios reales traería más frases distintas y más trabajo en la etapa de narrativas.

El pipeline no se toca: se corre el comando normal en otro proceso. Un vigilante lo corta si pasa el tope de
tiempo (que incluye armar los datos), si el proceso usa más de la mitad de la RAM de la máquina o si la RAM libre
del sistema queda por debajo del mínimo durante 10 segundos seguidos, para no trabar la computadora.
Todo se escribe en salida/verificacion/ (no se versiona).
"""
import argparse
import json
import shutil
import subprocess
import sys
import time

import duckdb
import psutil

from comun import PRACTICA, RAIZ, SALIDA, dec, puntuar

REGISTRO = SALIDA / "sintetico.json"


def armar(copias: int, carpeta) -> dict:
    """Escribe el set repetido y su verdad repetida igual. Todo por SQL, sin cargar nada en memoria de Python."""
    if carpeta.exists():
        shutil.rmtree(carpeta)
    (carpeta / "verdad").mkdir(parents=True)
    ruta = lambda p: str(p).replace("\\", "/").replace("'", "''")
    leer = lambda p: f"read_csv('{ruta(p)}', all_varchar=true, header=true)"
    escribir = lambda sql, p: con.execute(f"COPY ({sql}) TO '{ruta(p)}' (HEADER, DELIMITER ',')")
    con = duckdb.connect()
    con.execute("SET memory_limit='1GB'")
    con.execute(f"CREATE TEMP TABLE k AS SELECT i::INTEGER AS i, '_' || i AS s FROM range({int(copias)}) t(i)")
    dias = con.execute(f"SELECT date_diff('day', min(substr(fecha, 1, 10)::DATE), max(substr(fecha, 1, 10)::DATE)) + 1 "
                       f"FROM {leer(PRACTICA / 'comentarios.csv.gz')}").fetchone()[0]
    correr = lambda col: (f"strftime(substr({col}, 1, 19)::TIMESTAMP + to_days(k.i * {dias}), '%Y-%m-%dT%H:%M:%S') "
                          f"|| substr({col}, 20)")
    escribir(f"SELECT comentario_id || s AS comentario_id, publicacion_id || s AS publicacion_id, cuenta_id || s AS cuenta_id, "
             f"{correr('fecha')} AS fecha, texto, respuesta_a || s AS respuesta_a, me_gusta "
             f"FROM {leer(PRACTICA / 'comentarios.csv.gz')}, k ORDER BY k.i, comentario_id", carpeta / "comentarios.csv.gz")
    escribir(f"SELECT cuenta_id || s AS cuenta_id, usuario || s AS usuario, "
             f"strftime(fecha_creacion::DATE + to_days(k.i * {dias}), '%Y-%m-%d') AS fecha_creacion, seguidores, siguiendo "
             f"FROM {leer(PRACTICA / 'cuentas.csv.gz')}, k ORDER BY k.i, cuenta_id", carpeta / "cuentas.csv.gz")
    escribir(f"SELECT publicacion_id || s AS publicacion_id, fuente_id, {correr('fecha')} AS fecha, titular "
             f"FROM {leer(PRACTICA / 'publicaciones.csv.gz')}, k ORDER BY k.i, publicacion_id", carpeta / "publicaciones.csv.gz")
    shutil.copy(PRACTICA / "fuentes.csv", carpeta / "fuentes.csv")
    escribir(f"SELECT comentario_id || s AS comentario_id, narrativa_id, postura "
             f"FROM {leer(PRACTICA / 'verdad' / 'comentarios.csv.gz')}, k ORDER BY k.i, comentario_id",
             carpeta / "verdad" / "comentarios.csv.gz")
    escribir(f"SELECT cuenta_id || s AS cuenta_id, campana_id || s AS campana_id "
             f"FROM {leer(PRACTICA / 'verdad' / 'cuentas.csv.gz')}, k ORDER BY k.i, cuenta_id",
             carpeta / "verdad" / "cuentas.csv.gz")
    shutil.copy(PRACTICA / "verdad" / "narrativas.csv", carpeta / "verdad" / "narrativas.csv")
    cuenta = lambda p: con.execute(f"SELECT count(*) FROM {leer(p)}").fetchone()[0]
    datos = {"comentarios": cuenta(carpeta / "comentarios.csv.gz"), "cuentas": cuenta(carpeta / "cuentas.csv.gz"),
             "publicaciones": cuenta(carpeta / "publicaciones.csv.gz"), "dias": int(dias) * copias,
             "coordinadas_reales": con.execute(f"SELECT count(campana_id) FROM {leer(carpeta / 'verdad' / 'cuentas.csv.gz')}").fetchone()[0]}
    con.close()
    return datos


def correr_vigilado(orden: list, registro, limite: float, min_libre_mb: float, max_proceso_mb: float) -> dict:
    """Corre la orden y la corta si pasa la hora límite o si la memoria se pone peligrosa. Mide desde afuera."""
    inicio = time.perf_counter()
    pico = poco_libre = 0
    min_libre = psutil.virtual_memory().available / 2**20
    motivo = None
    with open(registro, "w", encoding="utf-8") as salida:
        proceso = subprocess.Popen(orden, cwd=RAIZ, stdout=salida, stderr=subprocess.STDOUT)
        while proceso.poll() is None:
            time.sleep(1)
            try:
                arbol = [psutil.Process(proceso.pid)] + psutil.Process(proceso.pid).children(recursive=True)
                usado = sum(p.memory_info().rss for p in arbol) / 2**20
            except psutil.Error:
                continue
            libre = psutil.virtual_memory().available / 2**20
            pico, min_libre = max(pico, usado), min(min_libre, libre)
            poco_libre = poco_libre + 1 if libre < min_libre_mb else 0
            if time.time() > limite:
                motivo = "pasó el tope de tiempo"
            elif usado > max_proceso_mb:
                motivo = f"el proceso llegó a {usado:.0f} MB (límite {max_proceso_mb:.0f} MB)"
            elif poco_libre >= 10:
                motivo = f"la RAM libre del sistema estuvo 10 s por debajo de {min_libre_mb:.0f} MB"
            if motivo:
                for p in reversed(arbol):
                    try:
                        p.kill()
                    except psutil.Error:
                        pass
                proceso.wait()
                break
    return {"cortado": motivo, "codigo": proceso.returncode, "reloj": round(time.perf_counter() - inicio, 1),
            "pico_externo_mb": round(pico), "ram_libre_minima_mb": round(min_libre)}


def correr(copias: int, tope_minutos: float, min_libre_mb: float):
    limite = time.time() + 60 * tope_minutos
    nombre = f"sintetico_x{copias}"
    carpeta = SALIDA / nombre
    memoria = psutil.virtual_memory()
    fila = {"copias": copias, "tope_minutos": tope_minutos, "ram_libre_inicio_gb": round(memoria.available / 2**30, 2)}
    inicio = time.perf_counter()
    fila.update(armar(copias, carpeta / "datos"))
    fila["segundos_armado"] = round(time.perf_counter() - inicio, 1)
    print(f"Set sintético: {fila['comentarios']} comentarios, {fila['cuentas']} cuentas, {fila['publicaciones']} publicaciones, "
          f"{fila['dias']} días, armado en {fila['segundos_armado']} s. RAM libre: {fila['ram_libre_inicio_gb']} GB.", flush=True)
    for viejo in (carpeta / "base.duckdb", carpeta / "base.duckdb.wal"):
        viejo.unlink(missing_ok=True)
    orden = [sys.executable, "-u", "-m", "pipeline.run", "--datos", str(carpeta / "datos"), "--entrega", str(carpeta / "entrega"),
             "--base", str(carpeta / "base.duckdb"), "--reporte", str(carpeta / "reporte.html")]
    fila.update(correr_vigilado(orden, carpeta / "salida.txt", limite, min_libre_mb, memoria.total / 2**20 / 2))
    registro = (carpeta / "salida.txt").read_text(encoding="utf-8", errors="replace")
    fila["etapas_terminadas"] = [l.split("]")[0][1:] for l in registro.splitlines() if l.startswith("[") and "]" in l]
    fila["termino"] = fila["cortado"] is None and fila["codigo"] == 0
    if fila["termino"]:
        costo = json.loads((carpeta / "entrega" / "costo.json").read_text(encoding="utf-8"))
        fila.update({"segundos": costo["segundos"], "memoria_pico_mb": costo["memoria_pico_mb"],
                     "base_mb": costo["almacenamiento_mb"]["base_duckdb"], "entrada_mb": costo["almacenamiento_mb"]["entrada_csv"],
                     "etapas": {k: v["segundos"] for k, v in costo["etapas"].items()},
                     "tope_coordinacion_activado": costo.get("tope_coordinacion", {}).get("activado"),
                     "puntaje": puntuar(carpeta / "datos" / "verdad", carpeta / "entrega")})
    else:
        fila["ultimas_lineas"] = registro.splitlines()[-8:]
    resultados = json.loads(REGISTRO.read_text(encoding="utf-8")) if REGISTRO.exists() else {}
    resultados[nombre] = fila
    REGISTRO.write_text(json.dumps(resultados, ensure_ascii=False, indent=1), encoding="utf-8")


def miles(n) -> str:
    return f"{int(n):,}".replace(",", ".")


def tabla() -> str:
    salida = []
    for nombre, f in json.loads(REGISTRO.read_text(encoding="utf-8")).items():
        salida.append(f"\n{nombre} (SINTÉTICO: práctica x{f['copias']}): {miles(f['comentarios'])} comentarios, {miles(f['cuentas'])} cuentas, "
                      f"{miles(f['publicaciones'])} publicaciones, {f['dias']} días. RAM libre al empezar: {dec(f['ram_libre_inicio_gb'], 1)} GB.")
        if not f["termino"]:
            salida.append(f"  NO TERMINÓ: {f['cortado'] or 'el pipeline terminó con error ' + str(f['codigo'])}, a los {f['reloj']} s. "
                          f"Etapas terminadas: {', '.join(f['etapas_terminadas']) or 'ninguna'}. Pico {f['pico_externo_mb']} MB, "
                          f"RAM libre mínima {f['ram_libre_minima_mb']} MB.")
            salida += ["    " + l for l in f["ultimas_lineas"]]
            continue
        p = f["puntaje"]
        salida.append(f"  Terminó: {dec(f['segundos'], 1)} s el pipeline ({miles(f['comentarios'] / f['segundos'])} comentarios por segundo), "
                      f"{dec(f['segundos_armado'], 1)} s armar los datos. Memoria pico {f['memoria_pico_mb']} MB "
                      f"(medida desde afuera: {f['pico_externo_mb']} MB; RAM libre mínima del sistema: {f['ram_libre_minima_mb']} MB). "
                      f"Base {dec(f['base_mb'], 1)} MB, entrada {dec(f['entrada_mb'], 1)} MB.")
        salida.append("  Etapas: " + ", ".join(f"{k} {dec(v, 1)} s" for k, v in f["etapas"].items()))
        salida.append(f"  Control contra la verdad repetida: total {dec(p['total'], 2)} / 55; agrupamiento {dec(p['agrup'])}, ruido {dec(p['ruido'])}, "
                      f"postura {dec(p['postura'])}, origen {dec(p['origen'], 2)}; coordinación P {dec(p['coord_p'], 2)} R {dec(p['coord_r'], 2)}, "
                      f"marcadas {p['marcadas']} de {f['coordinadas_reales']}, grupos {dec(p['grupos_f1'])}. "
                      f"Tope de seguridad activado: {'sí' if f['tope_coordinacion_activado'] else 'no'}.")
    return "\n".join(salida)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--copias", type=int, default=5, help="Cuántas veces repetir el set de práctica (5 = un millón)")
    ap.add_argument("--tope-minutos", type=float, default=15, help="Tope de todo el intento, con el armado de datos")
    ap.add_argument("--min-libre-mb", type=float, default=300, help="RAM libre mínima del sistema antes de cortar")
    ap.add_argument("--tabla", action="store_true")
    args = ap.parse_args()
    if not args.tabla:
        correr(args.copias, args.tope_minutos, args.min_libre_mb)
    print(tabla())
