# Silu — sistema personal de tickets

## 1. Resumen

Silu es un sistema personal para capturar ideas, tareas, gastos y pensamientos sueltos en el momento en que ocurren, sin fricción, y convertirlos en "tickets" que luego se revisan, editan y despachan hacia su destino final (una tarea, una base de Notion, un registro de gastos, etc.).

La captura ocurre principalmente por **audio** (mensaje de voz a un bot de Telegram) o por **texto** ("oye Silu, generame un ticket sobre..."). El sistema transcribe (si aplica), usa un LLM para generar un ticket legible, y lo deja pendiente de revisión. La revisión y el despacho ocurren después, en una web app, donde el usuario cataloga, edita y decide qué hacer con cada ticket — con ayuda de un agente lateral.

## 2. Problema que resuelve

Ideas, tareas y pensamientos surgen en cualquier momento del día y se pierden si no hay una forma rápida de capturarlos sin salir del flujo (por ejemplo, caminando o manejando). Silu separa dos momentos:

1. **Captura rápida** — sin pensar en categorías, carpetas ni destino. Solo grabar o escribir.
2. **Revisión con calma** — cuando hay tiempo, se procesan los tickets acumulados: se editan, se catalogan y se envían a donde corresponde (Notion, lista de tareas, planilla de gastos, etc.).

## 3. Ejemplos reales de tickets esperados

- Audio: "Me falta mandar un correo a Gloria para que gestione mi cheque por viaje" → ticket tipo tarea/recordatorio.
- Audio: "Dejo recordado trabajar en el tema de PowerQuery de tía Loro" → ticket tipo tarea.
- Audio: "Gasté 1.000 pesos en un helado" → ticket tipo gasto, que luego se catalogará manualmente como "comida" y se enviará a un registro de gastos.
- Audio: "Un buen ejemplo de poca sostenibilidad son Teotihuacán o la pesca industrial" → ticket tipo argumento/idea, para una hoja de argumentos sobre sostenibilidad.
- Texto directo: "Silu, generame un ticket sobre..." → mismo flujo, sin paso de transcripción.

El esquema de ticket es deliberadamente **genérico**: no hay tipos rígidos ni campos obligatorios distintos por categoría. Cualquier cosa que se le diga a Silu se convierte en un ticket con la misma estructura.

## 4. Flujo end-to-end

1. El usuario envía un audio o un texto al bot de Telegram.
2. El backend recibe el mensaje vía webhook.
3. Si es audio, se transcribe (servicio en la nube).
4. Un LLM toma la transcripción o el texto y genera `title` + `summary` (ver modelo de datos).
5. El ticket se guarda en la base de datos con estado `pendiente`.
6. El usuario abre la web app cuando tiene tiempo, revisa la bandeja de tickets pendientes.
7. Desde la web, con ayuda de un agente (panel lateral) que opera mediante skills, el usuario edita, cataloga, mueve o despacha cada ticket a su destino final.
8. El campo `resolution` queda registrado con lo que efectivamente se hizo con el ticket, y el estado pasa a `en_curso` o `archivado`.

## 5. Modelo de datos

Una sola tabla `tickets`, sin metadatos estructurados por tipo:

| Campo | Tipo | Descripción |
|---|---|---|
| `id` | UUID / serial | Identificador |
| `created_at` | timestamp | Fecha de creación |
| `updated_at` | timestamp | Última modificación |
| `raw_text` | text | Transcripción o texto original tal cual llegó. Accesible solo desde una opción secundaria en la UI, no es lo principal que se lee. |
| `title` | text | Título corto generado por el LLM |
| `summary` | text | **No es un resumen, es una descripción de la tarea/hecho en sí misma** — debe permitir entender de qué se trataba al releerlo después, sin necesitar el audio original. Esto es lo que el usuario realmente lee en la web. |
| `status` | enum | `pendiente` / `en_curso` / `archivado` |
| `resolution` | text | Texto libre que describe qué se hizo finalmente con el ticket (lo rellena el agente al despachar el ticket, ej. "Movido a Notion > Currículum", "Registrado como gasto de comida, $1.000") |

Decisión explícita: se descartó un campo de metadatos JSON por tipo de ticket, para no imponer una taxonomía rígida de antemano. La estructura vive en el destino final (Notion, planilla, etc.), no en la tabla de tickets.

## 6. Arquitectura

```
Telegram (audio o texto)
        ↓
Backend en VPS (FastAPI)
  — recibe webhook
  — transcribe (si aplica)
  — llama al LLM para generar title + summary
        ↓
Base de datos (Postgres)
  — tickets pendientes de revisión
        ↓
Web app (React)
  — bandeja de tickets
  — revisión, edición, catalogación
  — panel lateral con agente (opera vía skills)
        ↓
Destinos
  — páginas de Notion, listas de tareas, registros de gastos, hojas de argumentos, etc.
```

## 7. Stack tecnológico

- **Backend:** Python + FastAPI (ya conocido por el usuario vía el proyecto ICAI, reutiliza experiencia existente)
- **Base de datos:** PostgreSQL
- **Frontend:** React con Vite (sin necesidad de SSR/SEO, es una app privada de uso personal)
- **Transcripción y LLM:** servicios en la nube (ej. Groq para transcripción/LLM rápido y con tier gratis, o Claude/GPT si se prioriza calidad de resumen sobre costo). No se ejecutan modelos localmente.
- **Bot:** Telegram Bot API (oficial, gratuita, sin fricción de aprobación de negocio — a diferencia de WhatsApp Business API)
- **Infraestructura:** contenedores Docker (backend, DB, frontend/reverse proxy) sobre un único VPS

## 8. Infraestructura y costos

- **VPS:** Hetzner Cloud (línea CX, ~€4/mes) — suficiente para esta carga (mayormente idle, esperando webhooks y haciendo llamadas a APIs externas). Alternativa gratuita: Oracle Cloud Free Tier (instancia ARM), con más fricción de registro.
- **Dominio:** Porkbun o Cloudflare Registrar (~$8-10 USD/año, sin sobrecostos de renovación ocultos).
- **Reverse proxy / HTTPS:** Caddy (certificados automáticos, configuración mínima).
- **Costo total estimado:** ~$5-6 USD/mes incluyendo dominio prorrateado.

## 9. Ciclo de vida del ticket

- `pendiente` — recién creado, no revisado.
- `en_curso` — el usuario ya lo procesó parcialmente o está en seguimiento.
- `archivado` — despachado a su destino final; `resolution` documenta qué se hizo.

## 10. Agente y panel lateral (pendiente de detallar)

La revisión de tickets ocurre con ayuda de un agente en un panel lateral dentro de la web app, que opera mediante **skills** para manipular tickets: moverlos a un destino, agregarles información, cambiar su estado, catalogarlos, etc. El diseño detallado de qué skills existen y cómo se estructuran queda como siguiente paso de diseño, antes o durante la implementación.

## 11. Requisitos no funcionales / restricciones de diseño

- Un solo usuario (sin necesidad de multiusuario, roles ni permisos).
- Sin inferencia de modelos local — todo LLM/transcripción vía servicios en la nube.
- Prioridad en minimizar costo de infraestructura.
- El esquema de ticket debe mantenerse genérico; la estructura y taxonomía específica vive en los destinos (Notion, planillas, etc.), no en la tabla de tickets.
- Captura sin fricción: debe funcionar igual de bien por audio que por texto, desde el mismo bot de Telegram.

## 12. Próximos pasos

- Diseñar el conjunto de skills del agente lateral (qué acciones puede ejecutar sobre un ticket, cómo se conecta a Notion vía API/MCP, etc.)
- Definir el prompt del LLM que genera `title` y `summary` a partir de la transcripción/texto.
- Definir esquema inicial de la tabla `tickets` en Postgres (migraciones).
- Levantar el VPS, configurar dominio y Docker Compose base (backend, DB, frontend, Caddy).
- Configurar el bot de Telegram y el webhook.
