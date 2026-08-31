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

Luego mapea con los archivos existentes en `/DATA_AND_STRUCTURE` por coincidencia de nombres (los backups generados de producción). Toma el ultimo más reciente por base de datos, y a este archivo es al cual se le complemente el nombre con la terminación _test o similar (por coincidencia y existencia en bd).
Y así es que mantiene actualizada una base de datos de testing.

Su ejecución tiene un control que verifica que sea domingo, si no es domingo nada se ejecuta. Esto con el fin de prevenir ejecuciones indeseadas. Aún así, para probar el script o ejecutarlo en cualquier otro día, se puede usar la flag `--force`, es decir. Desde la terminal posicionarse en `/CRON` y ejecutar `python restore.py --force`

Así tambien podemos establecer los workers
`python restore.py --force --workers 4` o `python restore.py --force --workers=4`

**nota:** El máximo de workers está limitado a 6


## TEMPORALIDAD DE CRONS
- backup.py: `33 3 * * * /bin/python3 /home/<host>/BACKUPS_DATABASES/CRON/backup.py`
- restore.py `0 7 * * 0 /bin/python3 /home/<host>/BACKUPS_DATABASES/CRON/restore.py`

**nota:** para las 11 bases de datos actuales, el crón comenzó a las 3:33 y terminó a las 4:53. 
Eso nos deja un aproximado de entre 1:20 min ± 20 minutos. Estimamos que removiendo tablas de bup, 2, bup_`fecha` etc. Estas 
deberían reducir su tiempo de importación.

## OTRAS ACOTACIONES
Ambos scripts tienen acceso al filesystem y aplican comandos similares para la exportación e importación de testing.


## COMANDOS DE CONTINGENCIA AL 28-8-26
- ``