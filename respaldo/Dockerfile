# Misma imagen que la base: pg_dump tiene que ser de la misma versión mayor que
# el servidor, o se niega a sacar la copia. Además trae el servidor de
# Postgres, que la verificación usa para restaurar en una base desechable.
FROM postgres:18-alpine

# restic cifra y sube solo lo que cambió; rclone es el puente a Google Drive,
# que restic no habla directamente. jq lee la fecha de la última copia y
# tzdata la muestra en hora de Chile en el aviso.
RUN apk add --no-cache restic rclone curl jq tzdata

COPY comun.sh respaldar.sh verificar.sh probar.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/respaldar.sh /usr/local/bin/verificar.sh /usr/local/bin/probar.sh

# Sin root: la verificación levanta un Postgres propio con initdb, que se
# niega a correr como root, y el respaldo no necesita más que leer la base.
USER postgres
WORKDIR /tmp

# Sin ENTRYPOINT: el de la imagen de Postgres arrancaría un servidor. Cada
# servicio de compose dice qué script corre.
ENTRYPOINT []
