#!/usr/bin/env python3
# coding=UTF-8

import os
import re
import sys
import logging

from pathlib import Path
from datetime import datetime


CRON_DIR = Path(__file__).resolve().parent
ENV_FILE = CRON_DIR / ".env"
DATA_AND_STRUCTURE_DIR = CRON_DIR.parent / "DATA_AND_STRUCTURE"
STRUCTURE_DIR = CRON_DIR.parent / "STRUCTURE"
LOGS_DIR = CRON_DIR / "logs"

if not LOGS_DIR.is_dir():
    sys.exit(f"!! No existe la carpeta {LOGS_DIR}")
    
##### CONFIGURACIÓN DE LOGGING #####
# Un archivo de log por día. El formato incluye fecha, hora y minuto
# en cada línea, tal como se pidió para poder rastrear errores.

log_file = LOGS_DIR / (
    f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
)

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


logger.info("========================================")
logger.info("Prueba de logger iniciada")
logger.info(f"Archivo de log: {log_file}")
logger.warning("Mensaje de advertencia de prueba")
logger.error("Mensaje de error de prueba")
logger.info("Prueba finalizada")
logger.info("========================================")
    
    