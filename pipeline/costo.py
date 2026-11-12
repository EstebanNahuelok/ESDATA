"""costo.json: cuánto costó procesar el set, medido en la corrida (nada escrito a mano).

Las 8 claves del enunciado van tal cual. Se agregan algunas más (memoria pico, tamaños, tiempos por etapa,
versiones) porque el jurado evalúa costo, escala y almacenamiento.
"""
import os
import platform
import shutil
import subprocess
import sys
from importlib import metadata
from pathlib import Path

try:
    import psutil
except ImportError:  # sin psutil no se mide memoria, pero el pipeline corre igual
    psutil = None

LIBRERIAS = ("duckdb", "numpy", "scipy", "scikit-learn", "networkx", "pandas")


def memoria_mb() -> tuple:
    """(memoria actual, memoria pico) del proceso en MB, o (None, None) si no hay psutil."""
    if psutil is None:
        return None, None
    info = psutil.Process().memory_info()
    pico = getattr(info, "peak_wset", None)  # Windows
    if pico is None:
        try:
            import resource
            pico = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == "darwin" else 1024)
        except ImportError:
            pico = info.rss
    return round(info.rss / 2**20), round(pico / 2**20)


def _nombre_cpu() -> str:
    try:
        if sys.platform == "win32":
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as clave:
                return " ".join(str(winreg.QueryValueEx(clave, "ProcessorNameString")[0]).split())
        if sys.platform == "darwin":
            return subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True, text=True,
                                  timeout=5).stdout.strip()
        with open("/proc/cpuinfo", encoding="utf-8") as f:
            for linea in f:
                if linea.lower().startswith("model name"):
                    return " ".join(linea.split(":", 1)[1].split())
    except Exception:
        pass
    return platform.processor() or platform.machine()


def describir_hardware() -> str:
    """Una línea con el equipo donde corrió: tipo, CPU, núcleos, RAM y GPU. Todo detectado, nada fijo."""
    partes = []
    hilos = os.cpu_count()
    if psutil is not None:
        try:
            partes.append("notebook" if psutil.sensors_battery() is not None else "PC de escritorio o servidor")
        except Exception:
            pass
        nucleos = psutil.cpu_count(logical=False)
        partes.append(f"{_nombre_cpu()} ({nucleos} núcleos, {hilos} hilos)" if nucleos else f"{_nombre_cpu()} ({hilos} hilos)")
        partes.append(f"{round(psutil.virtual_memory().total / 2**30)} GB de RAM")
    else:
        partes.append(f"{_nombre_cpu()} ({hilos} hilos)")
    partes.append("con GPU disponible pero sin usarla (todo corre en CPU)" if shutil.which("nvidia-smi")
                  else "sin GPU (todo corre en CPU)")
    partes.append(f"{platform.system()} {platform.release()}")
    return ", ".join(partes)


def _tamano_mb(rutas) -> float:
    return round(sum(Path(r).stat().st_size for r in rutas if Path(r).is_file()) / 2**20, 1)


def _versiones() -> dict:
    versiones = {"python": platform.python_version()}
    for nombre in LIBRERIAS:
        try:
            versiones[nombre] = metadata.version(nombre)
        except metadata.PackageNotFoundError:
            pass
    return versiones


def armar_costo(comentarios: int, segundos: float, etapas: dict, archivos: list, base: Path, entrega: Path,
                avisos: list, semilla: int, hardware: str = None, tokens_ia: int = 0, usd_ia: float = 0.0) -> dict:
    base, entrega = Path(base), Path(entrega)
    _, pico = memoria_mb()
    mb_entrada = _tamano_mb(archivos)
    comprimida = any(str(a).endswith(".gz") for a in archivos)
    mb_base = _tamano_mb([base])
    mb_entrega = _tamano_mb(entrega / n for n in ("comentarios.csv", "narrativas.csv", "cuentas.csv"))
    notas = ["Sin IA generativa ni servicios externos: TF-IDF sobre textos únicos, agrupamiento por lotes y grafos, todo en CPU."]
    if pico is not None:
        notas.append(f"Memoria pico del proceso: {pico} MB.")
    if avisos:
        notas.append("Avisos de la corrida: " + "; ".join(avisos) + ".")
    return {
        "comentarios_procesados": int(comentarios),
        "segundos": round(float(segundos), 1),
        "tokens_ia": int(tokens_ia),
        "usd_ia": round(float(usd_ia), 4),
        "usd_por_mil_comentarios": round(float(usd_ia) / (comentarios / 1000), 6) if comentarios else 0.0,
        "hardware": hardware or describir_hardware(),
        "almacenamiento": (f"DuckDB local, un solo archivo de {mb_base} MB ({base.as_posix()}) con las tablas limpias y los "
                           f"resultados; entrada {mb_entrada} MB en CSV{' comprimido' if comprimida else ''}, entrega {mb_entrega} MB en CSV"),
        "notas": " ".join(notas),
        "memoria_pico_mb": pico,
        "comentarios_por_segundo": round(comentarios / segundos) if segundos else None,
        "almacenamiento_mb": {"entrada_csv": mb_entrada, "base_duckdb": mb_base, "entrega_csv": mb_entrega},
        "etapas": etapas,
        "semilla": int(semilla),
        "versiones": _versiones(),
    }
