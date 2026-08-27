#!/usr/bin/env python3
# coding=UTF-8
"""
Paso 1: leer CRON/.env e imprimir una variable de entorno.
Paso 2: conectarse a MySQL con las credenciales de .env
y listar las bases de datos disponibles (SHOW DATABASES;).
Paso 3: conectarse a MySQL con las credenciales de .env,
listar las bases de datos disponibles (SHOW DATABASES;)
y separarlas en BASES_PROD / BASES_TEST según el sufijo del nombre.
Paso 4: realizar el backup (datos+estructura) de las bases de PRODUCCIÓN,
logueando errores (por base de datos y de permisos) con fecha/hora
en BACKUPS_DATABASES/CRON/logs.
"""

import os
import re
import sys
import gzip
import random
import logging
import tempfile
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

##### BUSQUEDA Y RESOLUCIÓN DE .ENV + CARPETAS DEL PROYECTO #####

CRON_DIR = Path(__file__).resolve().parent
ENV_FILE = CRON_DIR / ".env"
DATA_AND_STRUCTURE_DIR = CRON_DIR.parent / "DATA_AND_STRUCTURE"
STRUCTURE_DIR = CRON_DIR.parent / "STRUCTURE"
LOGS_DIR = CRON_DIR / "logs"

if not ENV_FILE.is_file():
    sys.exit(f"!! No existe {ENV_FILE}. Copiá .env.example a .env primero.")

load_dotenv(ENV_FILE)

##### VERIFICAMOS EXISTENCIA DE LAS CARPETAS NECESARIAS #####
if not DATA_AND_STRUCTURE_DIR.is_dir():
    sys.exit(f"!! No existe la carpeta {DATA_AND_STRUCTURE_DIR}")

if not STRUCTURE_DIR.is_dir():
    sys.exit(f"!! No existe la carpeta {STRUCTURE_DIR}")

if not LOGS_DIR.is_dir():
    sys.exit(f"!! No existe la carpeta {LOGS_DIR}")

##### CONFIGURACIÓN DE LOGGING #####
# Un archivo de log por día. El formato incluye fecha, hora y minuto
# en cada línea, tal como se pidió para poder rastrear errores.
log_file = LOGS_DIR / f"backup_{datetime.now().strftime('%Y-%m-%d')}.log"

logger = logging.getLogger("sispoapp_backups")
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

##### VARIABLES: LISTADO DE SUFIJOS PARA EXCLUSIÓN Y BASES DE DATOS PROPIAS DEL MOTOR, MYSQL, Y ARRAYS #####
TEST_SUFFIXES = ("_test", "_testing", "_dev", "_develop", "_prueba", "_temp", "_temporal", "_tmp")
SYSTEM_DATABASES = ("information_schema", "mysql", "performance_schema", "sys")
MYSQL_USER = os.environ.get("MYSQL_USER")
MYSQL_PASS = os.environ.get("MYSQL_PASS")
MYSQL_HOST = os.environ.get("MYSQL_HOST", "localhost")
MYSQL_PORT = int(os.environ.get("MYSQL_PORT", "3306"))
BACKUPS_A_MANTENER = int(os.environ.get("BACKUPS_A_MANTENER", "3"))
BASES_PROD = []
BASES_TEST = []

if not MYSQL_USER or not MYSQL_PASS:
    logger.error("Faltan MYSQL_USER y/o MYSQL_PASS en .env")
    sys.exit("!! Faltan MYSQL_USER y/o MYSQL_PASS en .env")

##### CONEXIÓN A BD #####
try:
    conn = pymysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASS,
        connect_timeout=5,
    )
except pymysql.MySQLError as e:
    logger.error(f"No se pudo conectar a MySQL: {e}")
    sys.exit(f"!! No se pudo conectar a MySQL: {e}")

##### CONSULTA 1: traemos todas las bases de datos dinamicamente #####
try:
    with conn.cursor() as cursor:
        cursor.execute("SHOW DATABASES;")
        rows = cursor.fetchall()
except pymysql.MySQLError as e:
    logger.error(f"Error al ejecutar SHOW DATABASES: {e}")
    conn.close()
    sys.exit(f"!! Error al ejecutar SHOW DATABASES: {e}")
finally:
    conn.close()

TODAS_LAS_BASES = [row[0] for row in rows]

##### SEPARAMOS LAS BDS DE SISTEMA, PRODUCCIÓN, Y TESTING #####
for nombre in TODAS_LAS_BASES:
    if nombre in SYSTEM_DATABASES:
        continue
    if nombre.lower().endswith(TEST_SUFFIXES):
        BASES_TEST.append(nombre)
    else:
        BASES_PROD.append(nombre)

print(f"Bases de PRODUCCIÓN ({len(BASES_PROD)}):")
for nombre in BASES_PROD:
    print(f"  - {nombre}")

print(f"\nBases de TESTING/DEV ({len(BASES_TEST)}):")
for nombre in BASES_TEST:
    print(f"  - {nombre}")

##### FUNCIÓN PARA CREAR UN ARCHIVO TEMPORAL CON LAS CREDENCIALES #####
def make_mysql_defaults_file() -> Path:
    """
    Crea un archivo temporal con las credenciales para que mysqldump
    no reciba el usuario/clave por línea de comandos (evita que
    queden expuestos en `ps aux`).
    """
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

##### DETECCIÓN DE ERRORES DE PERMISOS EN LA SALIDA DE mysqldump #####
PERMISSION_ERROR_PATTERNS = (
    "access denied",
    "command denied",
    "permission denied",
)

def es_error_de_permisos(stderr_output: str) -> bool:
    salida = stderr_output.lower()
    return any(patron in salida for patron in PERMISSION_ERROR_PATTERNS)

##### FUNCIÓN PARA CORRER EL DUMP E IR GENERANDO UN COMPRIMIDO #####
def dump_database_gz(nombre: str, defaults_file: Path, destino_gz: Path) -> bool:
    """
    Equivalente a: mysqldump ... nombre | gzip > destino_gz
    Streamea la salida de mysqldump directo a un archivo .gz,
    sin escribir el .sql sin comprimir en disco en ningún momento.
    """
    cmd = [
        "mysqldump",
        f"--defaults-extra-file={defaults_file}",
        "--lock-tables=false",
        "--no-tablespaces",
        nombre,
    ]

    try:
        proceso = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )

        with gzip.open(destino_gz, "wb") as gz_out:
            while True:
                chunk = proceso.stdout.read(1024 * 1024)  # 1 MB por lectura
                if not chunk:
                    break
                gz_out.write(chunk)

        proceso.wait()
        stderr_output = proceso.stderr.read().decode(errors="replace").strip()
    except OSError as e:
        logger.error(f"No se pudo ejecutar mysqldump para la base '{nombre}': {e}")
        destino_gz.unlink(missing_ok=True)
        return False

    if proceso.returncode != 0:
        if es_error_de_permisos(stderr_output):
            logger.error(
                f"Permisos insuficientes del usuario '{MYSQL_USER}' sobre la "
                f"base '{nombre}': {stderr_output}"
            )
        else:
            logger.error(f"mysqldump falló para la base '{nombre}': {stderr_output}")
        destino_gz.unlink(missing_ok=True)
        return False

    return True


def dump_database_structure(nombre: str, defaults_file: Path, destino_sql: Path) -> bool:
    """
    Vuelca únicamente la estructura de la base de datos (--no-data),
    sin compresión. Se guarda directo como .sql plano.
    """
    cmd = [
        "mysqldump",
        f"--defaults-extra-file={defaults_file}",
        "--lock-tables=false",
        "--no-tablespaces",
        "--no-data",
        nombre,
    ]

    try:
        with open(destino_sql, "wb") as sql_out:
            resultado = subprocess.run(cmd, stdout=sql_out, stderr=subprocess.PIPE)
    except OSError as e:
        logger.error(f"No se pudo ejecutar mysqldump (estructura) para la base '{nombre}': {e}")
        destino_sql.unlink(missing_ok=True)
        return False

    if resultado.returncode != 0:
        stderr_output = resultado.stderr.decode(errors="replace").strip()
        if es_error_de_permisos(stderr_output):
            logger.error(
                f"Permisos insuficientes del usuario '{MYSQL_USER}' sobre la "
                f"estructura de la base '{nombre}': {stderr_output}"
            )
        else:
            logger.error(f"mysqldump (estructura) falló para la base '{nombre}': {stderr_output}")
        destino_sql.unlink(missing_ok=True)
        return False

    return True


def cleanup_old_backups(nombre: str, directorio: Path, mantener: int) -> None:
    """
    Conserva solo los `mantener` backups más recientes de `nombre`
    dentro de `directorio` (según fecha de modificación) y borra el resto.
    Matchea exactamente el patrón <nombre>_YYYY-MM-DD_NNN.sql.gz para no
    confundir, por ejemplo, 'clientes' con 'clientes_reportes'.
    """
    patron = re.compile(rf"^{re.escape(nombre)}_\d{{4}}-\d{{2}}-\d{{2}}_\d{{3}}\.sql\.gz$")

    try:
        archivos = [f for f in directorio.iterdir() if f.is_file() and patron.match(f.name)]
    except OSError as e:
        logger.error(f"No se pudo leer el directorio {directorio} para limpiar backups de '{nombre}': {e}")
        return

    archivos.sort(key=lambda f: f.stat().st_mtime, reverse=True)  # más nuevo primero

    for viejo in archivos[mantener:]:
        print(f"      Borrando backup viejo: {viejo.name}")
        try:
            viejo.unlink(missing_ok=True)
        except OSError as e:
            logger.error(f"No se pudo borrar el backup viejo '{viejo.name}' de '{nombre}': {e}")

##### CREACIÓN DEL ARCHIVO TEMPORAL #####
defaults_file = make_mysql_defaults_file()

##### EJECUCIÓN DE DUMP DE MYSQL #####
print("\nIniciando backup de bases de PRODUCCIÓN...")
try:
    for nombre in BASES_PROD:
        fecha = datetime.now().strftime("%Y-%m-%d")
        numero_random = str(random.randint(0, 999)).zfill(3)

        destino_gz = DATA_AND_STRUCTURE_DIR / f"{nombre}_{fecha}_{numero_random}.sql.gz"
        destino_estructura = STRUCTURE_DIR / f"{nombre}.sql"

        print(f"  (*) Backupeando {nombre} ...")

        try:
            gz_ok = dump_database_gz(nombre, defaults_file, destino_gz)
        except Exception as e:
            logger.error(f"Error inesperado al backupear la base '{nombre}': {e}")
            gz_ok = False

        if gz_ok:
            print(f"      OK (datos+estructura) -> {destino_gz}")

        cleanup_old_backups(nombre, DATA_AND_STRUCTURE_DIR, BACKUPS_A_MANTENER)

        try:
            estructura_ok = dump_database_structure(nombre, defaults_file, destino_estructura)
        except Exception as e:
            logger.error(f"Error inesperado al volcar la estructura de la base '{nombre}': {e}")
            estructura_ok = False

        if estructura_ok:
            print(f"      OK (solo estructura)  -> {destino_estructura}")

    print("\nBackup de bases de PRODUCCIÓN finalizado.")
finally:
    defaults_file.unlink(missing_ok=True)