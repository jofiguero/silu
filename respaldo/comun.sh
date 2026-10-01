# Lo que comparten respaldar.sh y verificar.sh. Se carga con `.`, no se corre.

# El repositorio de restic vive en la carpeta silu-respaldos del Drive. El
# remoto "gdrive" lo arma rclone con las variables RCLONE_CONFIG_GDRIVE_* del
# .env: así no hay un archivo de configuración que montar en el contenedor.
export RESTIC_REPOSITORY="${RESTIC_REPOSITORY:-rclone:gdrive:silu-respaldos}"
export RESTIC_CACHE_DIR=/tmp/restic-cache
export RCLONE_CONFIG_GDRIVE_TYPE=drive
# Solo los archivos que creó rclone: si alguien entra al servidor, la llave
# no le abre el resto del Drive.
export RCLONE_CONFIG_GDRIVE_SCOPE=drive.file

# Donde queda la copia antes de subirla. Ruta fija: restic guarda la ruta
# completa, y verificar.sh la pide por ese mismo nombre.
DIRECTORIO=/tmp/respaldo
ARCHIVO="$DIRECTORIO/silu.dump"

paso="arranque"

# Manda un mensaje por el bot de tickets. Nunca falla: un aviso que no sale
# no puede tapar el error que se quería avisar.
avisar() {
    if [ -z "${TELEGRAM_BOT_TOKEN:-}" ] || [ -z "${RESPALDO_TELEGRAM_CHAT_ID:-}" ]; then
        echo "AVISO SIN ENVIAR (falta TELEGRAM_BOT_TOKEN o RESPALDO_TELEGRAM_CHAT_ID): $1" >&2
        return 0
    fi
    # -o /dev/null: la respuesta de Telegram no aporta al log. El token va en
    # la URL, así que nunca se imprime el comando.
    curl -sS -o /dev/null --max-time 20 \
        --data-urlencode "chat_id=$RESPALDO_TELEGRAM_CHAT_ID" \
        --data-urlencode "text=$1" \
        "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/sendMessage" \
        || echo "No se pudo avisar por Telegram" >&2
}

# Al salir con error, avisa en qué paso quedó. Se registra con trap para que
# cualquier comando que falle --gracias a set -e-- termine aquí. El estado
# llega como argumento y no se lee de $? adentro: si el trap hace algo antes
# de llamarla, $? ya sería el de ese algo y el error pasaría por éxito.
al_salir_con_error() {
    estado=$1
    if [ "$estado" -ne 0 ]; then
        echo "FALLÓ en el paso: $paso" >&2
        avisar "⚠️ $2 falló en el paso «$paso». Revisa ~/respaldo.log en el servidor."
    fi
    exit "$estado"
}

requerir() {
    for variable in "$@"; do
        eval "valor=\${$variable:-}"
        if [ -z "$valor" ]; then
            echo "Falta la variable $variable en el .env" >&2
            return 1
        fi
    done
}
