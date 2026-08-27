# AUTOMATIZACIÓN DE BACKUPS Y RESTORES

## PROYECTO DE AUTOMATIZACIÓN EN MARIA DB y PYTHON

## TECNOLOGÍAS
- Python 3.9
- Mariadb 10.11.19
- .env files
- data logging

## FLUJO DE TRABAJO DE backup.py
El script `backup.py` básicamente toma las bases de datos existentes y a las cuales el usuario 
definido en `.env` (backups).

Parsea dichas bases de datos en un array y discrimina:
- Bases de datos de mariadb y de sistema
- Bases de datos de producción (las que importan)
- Bases de datos de testing

Toma solo los nombres de las bases de datos de producción, y realiza un dump + gzip para
generar archivos de backups y mantenerlos en el file system. para posteriormente importarlos o restaurarlos según sea conveniente.

## FLUJO DE TRABAJO DE restore.py
El script `restore.py` básicamente toma los nombres de bases de datos existentes con terminaciones
_test, _testing, _dev, _develop, _aux, _auxiliar, etc.

Luego mapea con los archivos existentes en `/DATA_AND_STRUCTURE` por coincidencia de nombres (los backups generados de producción). Toma el ultimo más reciente por base de datos, y a este archivo es al cual

Se le complemente el nombre con la terminación _test o similar (por coincidencia y existencia en bd).
Y así es que mantiene actualizada una base de datos de testing.


## TEMPORALIDAD DE CRONS
- backup.py: `33 3 * * * /bin/python3 /home/n782216/BACKUPS_DATABASES/CRON/backup.py`
- restore.py `0 7 * * 0 /bin/python3 /home/n782216/BACKUPS_DATABASES/CRON/restore.py`

## OTRAS ACOTACIONES
Ambos scripts tienen acceso al filesystem y aplican comandos similares para la exportación e importación de testing.