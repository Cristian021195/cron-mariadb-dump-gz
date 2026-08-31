# POLICITA DE BACKUPS

** Última modificación 31-7-26 **

## INTRODUCCIÓN

El presente documento indica en general pautas de ordenamiento para el mantenimiento y gestion de las bases de datos en el servidor *sispoapp*

No es obligatorio, pero lo ideal es mantener un orden en todo el directorio del servidor para asi evitar archivos basuras, temporales sin sentidos, backups temporales, archivos copia de otros a modo de "respaldo" salvo que sea extremadamente necesario.

El usuario de bases de datos siguiente será usado *ÚNICAMENTE* para manejar respaldos manuales y automaticos por cron en la brevedad. 

``` 
    USUARIO MYSQL
    USER: <db_user>
    PASS: <db_user_pass>
    
    USUARIO FTP - Recomendamos Filezilla
    USER: <ftp_user>
    PASS: <ftp_pass>
    SERVER: <ftp_host>
    PUERTO: 21
    FOLDER: /
    
```


## Procedimiento

Tener en cuenta que:  
1. Es *INDISPENSABLE* que cada base de datos nueva que se cree primero se le asigne los permisos con este usuario `<db_user>`, sino los backups dan error de permisos y no se realizan. Es decir, genera archivos de pocos KB, cuando normalmente deben tener varios MB o GB en formato tar.giz
2. A modo de ordenamiento (y se planteará un nuevo flujo de backups automatico) donde:
    a. Las nuevas bases de datos de producción tendran un nombre claro y consistente
    b. Las bases de datos para herramientas de testing tendran las siguientes terminaciones: `_test, _testing, _dev, _develop, _tmp, _temp, _temporal, _aux, _auxiliar` esto con el fin de que el nuevo flujo identifique cuales BD son las que realmente debe respaldar y asi ahorrar espacio evitando bases de datos innecesarias.
3. Luego de creada y asignada al usuario `<db_user>` cree el usuario para destinado a la aplicación o cadena de conexion con los permisos necesarios que necesite.


## Gestion de backups manuales   

Hasta ahora los backups de *sispo server* (o cualquier servidor). Son descargados manualmente, transferidos a este servidor via FTP. Se los sube en la carpeta de `migraciones 2026` o `backups_tmp` (carpeta semanticamente temporal), y dichos archivos son importados por terminal en el motor de base de datos.
1. Descargamos el backup `<bd-fecha>.tar.gz` en nuestra maquina local
2. Lo subimos por FTP a la carpeta mencioada arriba
3. Desde la terminal nos posicionamos en la carpeta donde pusimos el comprimido
4. Ejecutamos el comando `tar -xzOf <bd-fecha>.tar.gz <ruta/hasta/archivo ultimo nivel>.sql | mysql -u <db_user> -p <bd-creada-reciente>` si no muestra errores deberia quedar pensando la consola y podemos ir verificando desde otra terminal, logueados con la misma cuenta mysql y ejecutar SHOW PROCESSLIST;
5. Verificar siempre luego de una importación:
    a. Peso de la base de datos: debe ser similar o mayor
    b. Comparar la cantidad de tablas: deben ser la misma cantidad de tablas
    c. Verificar si existen triggers en determinadas tablas
    d. Probar algunas consultas "pesadas" para verificar que hayan indices, o verificar estructura de las tablas mas importantes

Ejemplo: `tar -xzOf <db_name>_data_2026-06-24_03_33_01.tar.gz home/sispoc5/backup_database/sqldump/<db_name>_data_2026-06-24_03_33_01.sql | mysql -u <db_user> -p <bd_test>`
Ejemplo sin compresión: `mysql -u <db_user> -p<db_user_pass> <db_test> < sispoc5_centrica.sql`

*nota: si los archivos tienen otra compresión, verificar que software o paquete instalar en la terminal o desde nuestra pc buscar siempre el formato `.gz`
*nota: verificar siempre si el comprimido `.tar.gz` o `.gz` no tiene subcarpetas, lo ideal es que lo primero que se vea sea la base de datos `.sql`


## Post creación e importación

Algunas bases de datos cuentan con rutinas (funciones y procedimientos), eventos o triggers. Las cuales por algún motivo al generarse el backup automatico no 
las esta incluyendo, por lo tanto. Luego de crear las bd e importar los backups
deben ejecutarse manualmente por sql. 

En la carpeta `/migraciones 2026/rutinas_triggers_eventos` estan los archivos `.sql` de las respectivas bd, y comentados en caso de ser necesario.

Ejemplo  de importación: `mysql -u <db_user> -p<db_user_pass> <db_test> < rutinas.sql`

*nota: en algunos prodedimientos pueden haber escrituras de .csv aunque la verificamos en producción y no funcionan. 
Ejemplo en `PROCEDURE crear_respaldo_consultable` de `rutinas_gestionpostal.sql` supuestamente hace escrituras de .csv 
`INTO OUTFILE '../../.././home/sispoc5/backup_trimestral/piezas.csv' ` pero verifiamos en la carpeta y esta vacía. 
Seguramente podemos prescindir de ellos como asi tambien aquellos inserts en `INSERT INTO sispoc5_gestionpostal_bk.backup_json` 
ya que dicha bd no existe y su similar indica _borrar sin registros que parezcan relevantes

Recordar verificar siempre luego de una importación:
1. Peso de la base de datos: debe ser similar o mayor
2. Comparar la cantidad de tablas: deben ser la misma cantidad de tablas
3. Verificar si existen triggers en determinadas tablas
4. Probar algunas consultas "pesadas" para verificar que hayan indices, o verificar estructura de las tablas mas importantes

*IMPORTANTE* tener en cuenta que no todas las rutinas estan presentes ya que muchas se crearon con otro usuario, entonces el full admin debería proporcionarnos dicha exportación


## Aclaraciones finales

Recordar que hasta ahora son recomendaciones y propuestas, el flujo se backup
automático se avisará por mensaje, mail o grupos.

** El documento está sujeto a modificaciones y mejoras **