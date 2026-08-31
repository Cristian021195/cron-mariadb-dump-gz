# POLICITA DE BACKUPS AUTOMATICOS Y FUNCIONAMINETO DEL CRON

## ESTRUCTURA DE CARPETAS
- `/CRON` Carpeta que contiene .env con las credenciales del usuario de backups, más el script main.py con el algoritmo de backup más /logs en caso de errores  
- `/STRUCTURE` Aqui se guardan los backups `<bd>.sql.gz` de unicamente las estructuras de las bases de datos sin datos
- `/DATA_AND_STRUCTURE` Aqui se guardan los backups `<bd>_<fecha>.sql.gz` propiamente dichos los cuales pueden importarse directamente 
- `/RUTINAS_TRIGGERS_EVENTOS` Es código sql ajustado a las bases de datos que le corresponden en sus respectivos ambientes /PROD y /TEST siempre verificar antes de ejecutar
- `/RUTINAS_TRIGGERS_EVENTOS` Es código sql ajustado a las bases de datos que le corresponden en sus respectivos ambientes /PROD y /TEST siempre verificar antes de ejecutar

## FUNCIONAMIENTO DEL CRON
El cron básicamente consta de:
- El usuario `backups` encargado de gestionar backups. Recordar dar permisos ante nuevas bases de datos
- Una consulta que trae todas las bases de datos en las que tiene permisos
- Una lógica de filtrado para bases de datos de sistema, producción y testing
- Realizado de dump + compresión gzip para bases de datos unicamente de producción
- Guardado de dichos backups solo hasta 3 copias del mismo (o sea 72 hs) para evitar ocupar espacio de más
- Temporalidad: se ejecuta todos los días a las 3:33 AM `/bin/python3 /home/<host>/BACKUPS_DATABASES/CRON/backup.py`

```mermaid
flowchart TD

    A["Cron (03:33 AM)"] --> B["Ejecutar main.py"]
    B --> C["Conectar como usuario backups"]
    C --> D["Obtener listado de bases de datos con permisos"]

    D --> E{"¿Quedan bases por procesar?"}

    E -->|Sí| F["Tomar siguiente base de datos"]
    F --> G{"¿Es una BD de sistema o termina en _test?"}

    G -->|Sí| H["Ignorar"]
    H --> E

    G -->|No| I["Generar dump (datos + estructura)"]
    I --> J["Comprimir con gzip"]
    J --> K["Guardar en /DATA_AND_STRUCTURE"]
    K --> L["Eliminar backups antiguos\nMantener máximo 3 copias (72 hs)"]

    L --> M["Generar dump solo de estructura"]
    M --> N["Guardar en /STRUCTURE\nReemplazar copia anterior"]

    N --> E

    E -->|No| O["Finalizar proceso"]

    P["Usuario backups"] -.-> C
```
