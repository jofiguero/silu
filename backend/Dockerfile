FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# El proceso no corre como root: si alguien logra ejecutar código dentro del
# contenedor, queda con los permisos mínimos.
RUN useradd --create-home --uid 1001 silu && chown -R silu:silu /app
USER silu

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
