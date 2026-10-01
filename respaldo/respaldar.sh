#!/bin/sh
# Copia de la base, cifrada, a Google Drive. Corre todas las noches por cron:
#   docker compose run --rm respaldo
#
# Si algo falla avisa por el bot de tickets. Si sale bien no dice nada: un
# mensaje diario que siempre dice lo mismo se deja de leer, y entonces el día
# que dice otra cosa tampoco se lee. El "sigo vivo" lo da verificar.sh una
# vez por semana.
set -eu
# Sin esto, una tubería solo falla si falla su último comando.
set -o pipefail

. /usr/local/bin/comun.sh
trap 'al_salir_con_error "$?" "El respaldo de Silu"' EXIT

paso="revisar la configuración"
requerir POSTGRES_USER POSTGRES_PASSWORD POSTGRES_DB RESTIC_PASSWORD RCLONE_CONFIG_GDRIVE_TOKEN

paso="sacar la copia de la base"
mkdir -p "$DIRECTORIO"
# Como el dueño de las tablas y no como silu_app: con seguridad por fila, el
# rol de la aplicación sin dueño declarado no ve ni una fila, y la copia
# saldría vacía sin que nada fallara.
#
# Sin comprimir: restic comprime por su cuenta, y sobre la copia cruda
# reconoce lo que no cambió de un día a otro y no lo vuelve a subir.
PGPASSWORD="$POSTGRES_PASSWORD" pg_dump \
    --host="${POSTGRES_HOST:-db}" \
    --username="$POSTGRES_USER" \
    --dbname="$POSTGRES_DB" \
    --format=custom \
    --compress=0 \
    --file="$ARCHIVO"

paso="preparar el repositorio en Drive"
# La primera vez el repositorio no existe y hay que crearlo. Si ya existe,
# init falla sin tocar nada, así que no hay riesgo de pisar las copias.
restic cat config >/dev/null 2>&1 || restic init

paso="subir la copia a Drive"
restic backup --host silu --tag diario "$ARCHIVO"

paso="borrar las copias viejas"
# Una semana día a día, un mes semana a semana y medio año mes a mes.
restic forget --host silu --keep-daily 7 --keep-weekly 4 --keep-monthly 6 --prune

rm -f "$ARCHIVO"
echo "Respaldo listo: $(date -u '+%Y-%m-%d %H:%M UTC')"
