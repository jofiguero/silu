FROM python:3.13-slim

# PYTHONPATH: sin esto, `python scripts/x.py` pone /app/scripts en sys.path en
# vez de /app, y el paquete `app` no se encuentra.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

WORKDIR /app

# Las dependencias de desarrollo (pytest) solo entran cuando se construye la
# imagen de tests, para que la de produccion no las cargue.
ARG INSTALL_DEV=false

COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements.txt && \
    if [ "$INSTALL_DEV" = "true" ]; then \
        pip install --no-cache-dir -r requirements-dev.txt; \
    fi

COPY . .

# El proceso no corre como root: si alguien logra ejecutar codigo dentro del
# contenedor, queda con los permisos minimos.
RUN useradd --create-home --uid 1001 silu && chown -R silu:silu /app
USER silu

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
