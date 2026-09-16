# Silu

Sistema personal para capturar ideas, tareas, gastos y pensamientos sueltos en el momento en que ocurren —caminando, manejando, sin salir del flujo— y convertirlos en tickets que después se revisan con calma y se despachan a su destino final.

La idea de fondo es separar dos momentos que normalmente se mezclan y se estorban:

1. **Capturar**, sin pensar en categorías ni carpetas. Un mensaje de voz a un bot de Telegram, o un texto.
2. **Revisar**, cuando hay tiempo. Una bandeja donde cada ticket se edita, se cataloga y se manda a donde corresponda: una página de Notion, una lista de tareas, un registro de gastos.

## Cómo funciona

```
Telegram (audio o texto)
        ↓
FastAPI  — recibe el webhook, transcribe si es audio,
           y le pide a un LLM que genere título y descripción
        ↓
Postgres — tickets pendientes de revisión
        ↓
Web app  — bandeja, edición y catalogación,
           con un agente lateral que opera vía skills
        ↓
Destinos — Notion, listas de tareas, registros de gastos
```

## Decisión de diseño central

El esquema de ticket es **deliberadamente genérico**: una sola tabla, sin tipos rígidos ni campos distintos por categoría. Un gasto, una idea y un recordatorio se guardan igual.

La razón es que imponer una taxonomía por adelantado obliga a clasificar en el momento de capturar, que es justo cuando no se quiere pensar. La estructura vive en el destino final —la base de Notion, la planilla de gastos—, no en la tabla de tickets.

El campo `summary` tampoco es un resumen: es una descripción autocontenida del hecho, pensada para que al releerla semanas después se entienda de qué se trataba sin volver al audio original.

## Stack

- **Backend:** Python + FastAPI
- **Base de datos:** PostgreSQL 18, migraciones con Alembic
- **Frontend:** React + Vite
- **Transcripción y LLM:** servicios en la nube, sin inferencia local
- **Bot:** Telegram Bot API
- **Infraestructura:** Docker Compose sobre un VPS, con Caddy como reverse proxy y HTTPS automático

## Estado

En construcción. Funcionando hoy: la infraestructura, la base de datos y el esquema de tickets. Pendientes: el backend, el bot y la web app.

Los detalles de diseño están en [silu-contexto-proyecto.md](silu-contexto-proyecto.md).

## Correr el proyecto

```bash
cp .env.example .env     # y rellenar las variables
docker compose up -d db
docker compose run --rm migrate
```
