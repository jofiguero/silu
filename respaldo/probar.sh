#!/bin/sh
# Prueba de punta a punta sin tocar Drive ni mandar avisos:
#   docker compose run --rm --build respaldo probar.sh
#
# Saca la copia real de la base, la guarda en un repositorio local que muere
# con el contenedor, y la verifica restaurándola. Ejercita todo menos la
# subida a Drive, así que sirve antes de tener las credenciales.
set -eu

export RESTIC_REPOSITORY=/tmp/repositorio-de-prueba
export RESTIC_PASSWORD=solo-para-la-prueba
# requerir() la exige, pero con un repositorio local rclone no se usa.
export RCLONE_CONFIG_GDRIVE_TOKEN=no-se-usa
# Vacío: los avisos se imprimen en vez de llegar al teléfono.
export RESPALDO_TELEGRAM_CHAT_ID=

respaldar.sh
verificar.sh
