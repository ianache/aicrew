# 🤖 AIAgentsCrew — Multi-Agent Platform & TUI Telemetry

AIAgentsCrew es una plataforma de orquestación multiagente de alto rendimiento y grado de producción que aprovecha el **Google ADK** y la API de **Google Gemini** para planificar, ejecutar y sintetizar planes complejos en paralelo, visualizándolos en tiempo real a través de un elegante panel TUI (Terminal User Interface).

---

## 🌟 Características Principales

*   **Planificación Estructurada (Pass 1)**: Gemini analiza el requerimiento del usuario y genera un Grafo Acíclico Dirigido (DAG) optimizado con tareas específicas, agentes especialistas y sus dependencias técnicas.
*   **Aprobación Interactiva del Plan**: Si está activo, el orquestador presenta de forma amigable la propuesta del plan al usuario para su aprobación previa por consola antes de la ejecución.
*   **Telemetría y Dashboard en Tiempo Real (TUI)**: Una pantalla de consola interactiva libre de parpadeo alimentada por `rich.live` que monitoriza en directo:
    *   **Pipeline de Ejecución**: Tarea, agente asignado, skill activo y estado actual de cada tarea.
    *   **Progreso Global**: Barra de progreso del flujo de tareas completadas.
    *   **Feed de Pensamiento de Agentes**: Un feed dinámico que expone el razonamiento interno y las acciones en vivo del subagente activo.
*   **Ejecución Paralela y Aislamiento de Contexto (A2A)**: Despacha tareas independientes concurrentemente utilizando `asyncio.gather` en contextos de ejecución aislados para modelar interacciones seguras.
*   **Recuperación Automática (Micro-Replanning)**: Si un subagente falla, el orquestador replanifica y re-instruye la tarea automáticamente en tiempo real (hasta 3 reintentos antes de marcar el fallo).
*   **Síntesis Ejecutiva Final (Pass 2)**: Consolida todo el registro de ejecución de las tareas y compila un reporte final ejecutivo y limpio para el usuario.

---

## 📋 Arquitectura Visual de la Terminal

El ciclo de vida del orquestador está diseñado para lucir increíble e interactivo en consola:

```
┌────────────────────────────────────────────────────────────────────────┐
│  🤖 CrewAI Execution Telemetry                                          │
│  🎯 Objetivo Global: "evaluar la especificacion del test case 5682..." │
│  📊 Estado General: ⏳ EN EJECUCIÓN                                     │
├────────────────────────────────────────────────────────────────────────┤
│  ID      PASO / TAREA         AGENTE        SKILL / HERRAMIENTA  ESTADO│
│ ────────────────────────────────────────────────────────────────────── │
│  task_01 Extract Test Data    DataAnalyst   GitLabMetricsTool   ✅ COMP...│
│  task_02 Audit Specification  ReporterAgent PolicyAuditTool     ⏳ RUNN...│
│  task_03 Consolidate Report   DataAnalyst   -                   💤 PEND...│
├────────────────────────────────────────────────────────────────────────┤
│  Progreso Global: [████████████████░░░░░░░░░░░░░░░░] 33%                │
├────────────────────────────────────────────────────────────────────────┤
│  💬 Pensamiento de los Agentes en Vivo (Últimos 4 logs):               │
│  [10:04:12] DataAnalystAgent: Analizando inputs y aplicando metrics... │
│  [10:04:15] DataAnalystAgent: Procesando y estructurando resultados... │
│  [10:04:18] ReporterAgent: Inicializando contexto de ejecución...      │
│  [10:04:20] ReporterAgent: Analizando inputs y aplicando auditoría...  │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 🚀 Guía de Inicio Rápido

### Requisitos Previos

*   **Python >= 3.13**
*   **UV** (Recomendado para la gestión ultrarrápida de dependencias de Python)

### 1. Clonar e Instalar Dependencias

Clona el repositorio e instala el entorno virtual con todas las dependencias del proyecto:

```bash
# Sincronizar e instalar dependencias con uv
uv sync
```

### 2. Configurar Variables de Entorno

Crea un archivo `.env` en la raíz del proyecto basándote en `.env.example`:

```env
# Clave de API obligatoria de Google Gemini
GEMINI_API_KEY="tu_gemini_api_key_aqui"

# Opcional (Evita limitaciones de cuotas de la API de GitHub al resolver skills)
GITHUB_TOKEN="tu_github_token_personal"
```

### 3. Ejecutar los Agentes

Para iniciar la consola REPL del orquestador de agentes, ejecuta el siguiente comando:

```bash
uv run python main.py --allow-env --approve-plan
```

#### Parámetros Disponibles en el CLI:
*   `--approve-plan`: (Por defecto `True`) Requiere la confirmación interactiva por consola del plan elaborado por el planificador antes de proceder con las tareas.
*   `--allow-env`: Permite que la configuración del orquestador se lea de las variables de entorno locales.

---

## 🛠️ Resolución de Problemas Comunes

### Error: `ResourceExhausted` (429 - Quota Exceeded)

Al utilizar el nivel gratuito de la clave de la API de Google Gemini, es posible que encuentres un error similar al siguiente:
```
google.genai.errors.APIError: [429] Resource has been exhausted (e.g. queries per minute limit).
```

**Solución**: 
1. **Espera de restablecimiento**: La API gratuita de Gemini limita el número de solicitudes por minuto (RPM) y solicitudes por día (RPD). Espera de 30 a 60 segundos antes de volver a ejecutar el comando.
2. **Llave de producción / Pago por uso**: Para entornos de producción o pruebas continuas intensivas, asocia una cuenta de facturación en Google AI Studio para pasar a la capa de pago por uso (*Pay-as-you-go*) que elimina estas limitaciones de cuotas.
3. **Optimización del orquestador**: Nuestra nueva arquitectura de planificación desacoplada (`PlannerPlan`) reduce los tokens y payloads enviados por solicitud de forma dramática, minimizando la probabilidad de exceder las cuotas en comparación con las arquitecturas tradicionales.

### Verificar la Integridad del Sistema

Puedes correr la suite completa de pruebas unitarias e integradoras en cualquier momento para comprobar el correcto funcionamiento del orquestador:

```bash
uv run pytest --ignore=tests/test_e2e.py
```
