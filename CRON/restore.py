#!/usr/bin/env python3
# coding=UTF-8
"""
restore.py

Toma el ÚLTIMO backup .sql.gz generado por backup.py para cada base de
PRODUCCIÓN (DATA_AND_STRUCTURE/<nombre>_YYYY-MM-DD_NNN.sql.gz) y lo importa
en su base de testing correspondiente (<nombre>_<sufijo>), que debe existir
previamente en el servidor.

Pensado para correr por cron una vez por semana (domingos). Por defecto el
script se niega a correr si hoy no es domingo; usar --force para saltarse
ese chequeo (útil para pruebas manuales).
"""

import os
import re
import sys
import gzip
import tempfile
import logging
import argparse
import subprocess
from pathlib import Path
from datetime import datetime

##### VERIFICACIÓN DE DEPENDENCIAS #####

try:
    from dotenv import load_dotenv
except ImportError:
    sys.exit(
        "!! Falta python-dotenv. Instalalo con:\n"
        "   pip install python-dotenv"
    )

try:
    import pymysql
except ImportError:
    sys.exit(
        "!! Falta pymysql. Instalalo con:\n"
        "   pip install pymysql"
    )

##### ARGUMENTOS #####

parser = argparse.ArgumentParser(description="Restaura el último backup de cada base en su base de testing.")
parser.add_argument(
    "--force",
    action="store_true",
    help="Ejecutar aunque hoy no sea domingo (para pruebas manuales).",
)
args = parser.parse_args()

if not args.force and datetime.now().weekday() != 6:  # 0=lunes ... 6=domingo
    print("Hoy no es domingo: no se ejecuta la restauración (usar --force para forzar).")
    sys.exit(0)

##### BUSQUEDA Y RESOLUCIÓN DE .ENV + CARPETAS DEL PROYECTO #####

CRON_DIR = Path(__file__).resolve().parent
ENV_FILE = CRON_DIR / ".env"
DATA_AND_STRUCTURE_DIR = CRON_DIR.parent / "DATA_AND_STRUCTURE"
LOGS_DIR = CRON_DIR / "logs"

if not ENV_FILE.is_file():
    sys.exit(f"!! No existe {ENV_FILE}. Copiá .env.example a .env primero.")

load_dotenv(ENV_FILE)

if not DATA_AND_STRUCTURE_DIR.is_dir():
    sys.exit(f"!! No existe la carpeta {DATA_AND_STRUCTURE_DIR}")

if not LOGS_DIR.is_dir():
    sys.exit(f"!! No existe la carpeta {LOGS_DIR}")

##### CONFIGURACIÓN DE LOGGING (mismo esquema que backup.py) #####

log_file = LOGS_DIR / f"restore_{datetime.now().strftime('%Y-%m-%d')}.log"

logger = logging.getLogger("sispoapp_restores")
logger.setLevel(logging.INFO)

formatter = logging.Formatter(
    fmt="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M",
)

file_handler = logging.FileHandler(log_file, encoding="utf-8")
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

##### VARIABLES DE CONEXIÓN Y CLASIFICACIÓN DE BASES #####

TEST_SUFFIXES = (
    "_testing",
    "_develop",
    "_temporal",
    "_auxiliar",
    "_prueba",
    "_temp",
    "_test",
    "_dev",
    "_tmp",
    "_aux",
)
SYSTEM_DATABASES = ("information_schema", "mysql", "performance_schema", "sys")
MYSQL_USER = os.environ.get("MYSQL_USER")
MYSQL_PASS = os.environ.get("MYSQL_PASS")
MYSQL_HOST = os.environ.get("MYSQL_HOST", "localhost")
MYSQL_PORT = int(os.environ.get("MYSQL_PORT", "3306"))

if not MYSQL_USER or not MYSQL_PASS:
    logger.error("Faltan MYSQL_USER y/o MYSQL_PASS en .env")
    sys.exit("!! Faltan MYSQL_USER y/o MYSQL_PASS en .env")

##### PATRÓN DE NOMBRE DE ARCHIVO (mismo formato que genera backup.py) #####
# <nombre>_YYYY-MM-DD_NNN.sql.gz
FILENAME_PATTERN = re.compile(r"^(?P<nombre>.+)_\d{4}-\d{2}-\d{2}_\d{3}\.sql\.gz$")


def encontrar_ultimo_backup_por_base(directorio: Path) -> dict:
    """
    Recorre el directorio de backups y arma un diccionario
    { nombre_base_produccion: Path_al_archivo_mas_reciente }.
    "Más reciente" se decide por fecha de modificación del archivo,
    no por el número random del nombre (ese no indica orden).
    """
    ultimos = {}  # nombre -> (mtime, Path)

    try:
        archivos = [f for f in directorio.iterdir() if f.is_file()]
    except OSError as e:
        logger.error(f"No se pudo leer el directorio {directorio}: {e}")
        return {}

    for f in archivos:
        m = FILENAME_PATTERN.match(f.name)
        if not m:
            continue
        nombre = m.group("nombre")
        mtime = f.stat().st_mtime
        if nombre not in ultimos or mtime > ultimos[nombre][0]:
            ultimos[nombre] = (mtime, f)

    return {nombre: path for nombre, (_, path) in ultimos.items()}


def obtener_base_produccion(nombre: str):
    """Devuelve la base productiva asociada a un sufijo testing final."""
    nombre_lower = nombre.lower()

    for sufijo in TEST_SUFFIXES:
        if nombre_lower.endswith(sufijo):
            base = nombre[: -len(sufijo)]
            return base or None

    return None


##### FUNCIÓN PARA CREAR UN ARCHIVO TEMPORAL CON LAS CREDENCIALES #####
# (idéntica a la de backup.py: evita pasar user/clave por línea de comandos)
def make_mysql_defaults_file() -> Path:
    fd, path = tempfile.mkstemp(prefix="mysql_defaults_", suffix=".cnf")
    contenido = (
        "[client]\n"
        f"user={MYSQL_USER}\n"
        f"password={MYSQL_PASS}\n"
        f"host={MYSQL_HOST}\n"
        f"port={MYSQL_PORT}\n"
    )
    with os.fdopen(fd, "w") as f:
        f.write(contenido)
    os.chmod(path, 0o600)
    return Path(path)


def obtener_bases_existentes() -> set:
    """Devuelve las bases visibles para el usuario configurado."""
    try:
        conn = pymysql.connect(
            host=MYSQL_HOST,
            port=MYSQL_PORT,
            user=MYSQL_USER,
            password=MYSQL_PASS,
            connect_timeout=5,
        )
    except pymysql.MySQLError as e:
        logger.error(f"No se pudo conectar a MySQL para listar bases: {e}")
        sys.exit(f"!! No se pudo conectar a MySQL: {e}")

    try:
        with conn.cursor() as cursor:
            cursor.execute("SHOW DATABASES;")
            rows = cursor.fetchall()
    finally:
        conn.close()

    return {row[0] for row in rows}


##### DETECCIÓN DE ERRORES DE PERMISOS (mismo criterio que backup.py) #####
PERMISSION_ERROR_PATTERNS = (
    "access denied",
    "command denied",
    "permission denied",
)


def es_error_de_permisos(stderr_output: str) -> bool:
    salida = stderr_output.lower()
    return any(patron in salida for patron in PERMISSION_ERROR_PATTERNS)


##### FUNCIÓN PARA IMPORTAR UN .sql.gz A UNA BASE #####
def importar_backup_gz(nombre_test: str, archivo_gz: Path, defaults_file: Path) -> bool:
    """
    Equivalente a: gunzip -c archivo_gz | mysql nombre_test
    Descomprime en memoria y streamea directo al stdin de mysql,
    sin escribir el .sql plano en disco.
    """
    cmd = ["mysql", f"--defaults-extra-file={defaults_file}", nombre_test]

    try:
        proceso = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE
        )

        with gzip.open(archivo_gz, "rb") as gz_in:
            while True:
                chunk = gz_in.read(1024 * 1024)  # 1 MB por lectura
                if not chunk:
                    break
                proceso.stdin.write(chunk)

        proceso.stdin.close()
        proceso.wait()
        stderr_output = proceso.stderr.read().decode(errors="replace").strip()
    except OSError as e:
        logger.error(f"No se pudo ejecutar mysql para importar en '{nombre_test}': {e}")
        return False
    except BrokenPipeError:
        # mysql cortó la conexión antes de tiempo (por ej. error grave de sintaxis)
        proceso.wait()
        stderr_output = proceso.stderr.read().decode(errors="replace").strip()
        logger.error(f"mysql cerró la conexión antes de tiempo importando '{nombre_test}': {stderr_output}")
        return False

    if proceso.returncode != 0:
        if es_error_de_permisos(stderr_output):
            logger.error(
                f"Permisos insuficientes del usuario '{MYSQL_USER}' sobre la "
                f"base '{nombre_test}': {stderr_output}"
            )
        else:
            logger.error(f"Import falló para la base '{nombre_test}': {stderr_output}")
        return False

    return True


##### EJECUCIÓN #####

defaults_file = make_mysql_defaults_file()

try:
    bases_existentes = obtener_bases_existentes()
    bases_testing_candidatas = []
    bases_produccion = set()

    for nombre in sorted(bases_existentes):
        if nombre.lower() in SYSTEM_DATABASES:
            continue

        base_produccion = obtener_base_produccion(nombre)
        if base_produccion:
            bases_testing_candidatas.append((nombre, base_produccion))
        else:
            bases_produccion.add(nombre)

    bases_testing = []
    for nombre_test, nombre_prod in bases_testing_candidatas:
        if nombre_prod not in bases_produccion:
            logger.error(
                f"La base testing '{nombre_test}' no tiene una base de produccion "
                f"correspondiente llamada '{nombre_prod}'. Se omite."
            )
            continue
        bases_testing.append((nombre_test, nombre_prod))

    if not bases_testing:
        logger.warning("No se encontraron bases de testing con un sufijo reconocido.")
        sys.exit(0)

    ultimos_backups = encontrar_ultimo_backup_por_base(DATA_AND_STRUCTURE_DIR)
    print(f"Bases de TESTING detectadas ({len(bases_testing)}):")
    for nombre_test, nombre_prod in bases_testing:
        print(f"  - {nombre_test} <- {nombre_prod}")

    print(f"\nIniciando restauración desde backups disponibles...")
    restauraciones = 0

    for nombre_test, nombre_prod in bases_testing:
        archivo_gz = ultimos_backups.get(nombre_prod)
        if archivo_gz is None:
            logger.error(
                f"No se encontró un backup para la base de produccion "
                f"'{nombre_prod}', asociada a '{nombre_test}'. Se omite."
            )
            continue

        print(f"  (*) Restaurando {archivo_gz.name} -> {nombre_test} ...")

        try:
            ok = importar_backup_gz(nombre_test, archivo_gz, defaults_file)
        except Exception as e:
            logger.error(f"Error inesperado al restaurar '{nombre_test}': {e}")
            ok = False

        if ok:
            restauraciones += 1
            print(f"      OK -> {nombre_test} actualizada desde {archivo_gz.name}")

    print(f"\nRestauración de bases de TESTING finalizada ({restauraciones}/{len(bases_testing)}).")
finally:
    defaults_file.unlink(missing_ok=True)
