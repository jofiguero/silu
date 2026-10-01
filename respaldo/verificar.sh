#!/bin/sh
# Comprueba que la última copia sirve: la baja de Drive y la restaura entera.
# Corre una vez por semana por cron:
#   docker compose run --rm verificar-respaldo
#
# Restaura en un Postgres que levanta dentro del mismo contenedor y que muere
# con él, no en el de producción: verificar no puede dejar nada atrás ni
# cargar la base que atiende la aplicación.
#
# Avisa siempre, salga bien o mal. Es el "sigo vivo" del respaldo: si un
# domingo no llega el mensaje, algo dejó de correr, aunque sea el cron.
set -eu
# Sin esto, una tubería solo falla si falla su último comando.
set -o pipefail

. /usr/local/bin/comun.sh
trap 'estado=$?; detener_postgres; al_salir_con_error "$estado" "La verificación del respaldo de Silu"' EXIT

PGLOCAL=/tmp/pg-verificacion
# Más vieja que esto, el respaldo diario dejó de correr aunque no haya avisado.
MAXIMO_HORAS=36

detener_postgres() {
    if [ -f "$PGLOCAL/postmaster.pid" ]; then
        pg_ctl -D "$PGLOCAL" -m immediate stop >/dev/null 2>&1 || true
    fi
}

paso="revisar la configuración"
requerir RESTIC_PASSWORD RCLONE_CONFIG_GDRIVE_TOKEN

paso="leer la fecha de la última copia"
# El contenedor corre en UTC, así que restic escribe la hora con Z y jq la
# puede leer: fromdateiso8601 no entiende fracciones de segundo ni otros husos.
tomada=$(restic snapshots --host silu --latest 1 --json \
    | jq -r 'last.time | sub("\\.[0-9]+Z$"; "Z") | fromdateiso8601')
horas=$(( ($(date +%s) - tomada) / 3600 ))
cuando=$(TZ=America/Santiago date -d "@$tomada" '+%d-%m %H:%M')
if [ "$horas" -gt "$MAXIMO_HORAS" ]; then
    paso="revisar la antigüedad (la última copia es del $cuando, hace $horas horas)"
    exit 1
fi

paso="revisar la integridad del repositorio"
restic check

paso="bajar la última copia"
mkdir -p "$DIRECTORIO"
restic dump --host silu latest "$ARCHIVO" > "$ARCHIVO"

paso="levantar un Postgres desechable"
initdb -D "$PGLOCAL" --username=postgres --auth=trust >/dev/null
# Solo por socket y sin puerto: nadie más tiene por qué alcanzarlo.
pg_ctl -D "$PGLOCAL" -o "-k /tmp -c listen_addresses=''" -w start >/dev/null

paso="restaurar la copia"
createdb -h /tmp -U postgres silu
# Sin dueños ni permisos: los roles de producción no existen aquí, y lo que se
# comprueba son los datos. --exit-on-error: una restauración a medias es una
# copia que no sirve, y tiene que fallar en vez de pasar callada.
pg_restore -h /tmp -U postgres -d silu --no-owner --no-acl --exit-on-error "$ARCHIVO"

paso="contar lo restaurado"
contar() {
    psql -h /tmp -U postgres -d silu -tAc "SELECT count(*) FROM $1"
}
usuarios=$(contar users)
if [ "$usuarios" -eq 0 ]; then
    paso="contar lo restaurado (la copia no tiene ninguna cuenta)"
    exit 1
fi
version=$(psql -h /tmp -U postgres -d silu -tAc "SELECT version_num FROM alembic_version")

resumen="tickets $(contar tickets), tareas $(contar thread_tasks), gastos $(contar expenses), prompts $(contar prompts), reuniones $(contar meetings)"

detener_postgres
rm -f "$ARCHIVO"

avisar "✅ Respaldo de Silu verificado. La copia del $cuando se restauró completa (migración $version): $resumen."
echo "Verificación lista: copia del $cuando, $resumen"
