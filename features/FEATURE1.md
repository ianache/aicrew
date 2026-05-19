# Documento de Requisitos de Producto (PRD)
## **PRD-004: Orquestador Multiagente Determinista (Plan-and-Execute)**
 * **Estado:** En Revisión
 * **Autor:** Ilver Anache (Application Architect / Project Manager)
 * **Fecha:** 17 de Mayo, 2026
 * **Framework Base:** Google Agent Development Kit (ADK)
## 1. Objetivos del Producto y Visión General
### 1.1. Visión del Producto
El objetivo de este feature es implementar un patrón de arquitectura **Plan-and-Execute** dentro de nuestra plataforma basada en agentes de IA. Esto permitirá resolver solicitudes complejas de los usuarios mediante la generación de un plan estructurado (DAG), el cual será delegado de forma controlada a subagentes especialistas, aislando sus contextos de ejecución y garantizando una respuesta final consolidada, limpia y de alta calidad.
### 1.2. Objetivos de Negocio (KPIs)
 * **Eficiencia de Contexto:** Reducir en un **40%** el consumo de tokens en el hilo de conversación principal con el cliente al aislar las ejecuciones intermedias en subagentes.
 * **Trazabilidad:** Lograr el **100%** de auditoría sobre los pasos lógicos que sigue la IA para resolver una consulta (cumpliendo con estándares de seguridad y Gobierno de Datos).
 * **Tasa de Éxito de Tareas:** Incrementar al **92%** la resolución correcta de peticiones complejas multi-paso gracias a la re-planificación y manejo de errores aislado.
## 2. Historias de Usuario
 * **Como** Usuario del Sistema,
   **quiero** enviar una solicitud compleja que involucre múltiples pasos de negocio,
   **para** recibir una única respuesta consolidada de nivel ejecutivo sin ver el ruido técnico o logs intermedios de procesamiento.
 * **Como** Administrador del Sistema / Arquitecto,
   **quiero** que el plan generado por la IA se registre en una estructura JSON fuertemente tipada y con estados mutables por herramientas,
   **para** poder auditar, pausar, o reintentar tareas específicas en caso de fallos.
 * **Como** Desarrollador de DevOps / IA,
   **quiero** que las ejecuciones de los subagentes corran en sub-hilos (hilos de contexto independientes),
   **para** evitar el desbordamiento o la contaminación de la ventana de contexto (*context window*) del agente coordinador.
## 3. Requisitos Funcionales (FR)
### 3.1. Módulo del Agente Coordinador (Orquestador)
 * **FR-1.1:** El Coordinador debe utilizar un modelo avanzado (gemini-3.0-pro o equivalente) capaz de realizar razonamiento complejo y llamadas a funciones estructuradas (*Structured Function Calling*).
 * **FR-1.2:** Ante una petición, el Coordinador tendrá la obligación de evaluar y generar un objeto ExecutionPlan validado mediante Pydantic.
 * **FR-1.3:** El Coordinador no podrá responder al usuario final hasta que el estado global del plan sea COMPLETED o FAILED de forma definitiva.
### 3.2. Motor de Gestión de Estado y Planes (Skill Toolset)
 * **FR-2.1:** Se debe implementar una Skill nativa de ADK (PlanManagementSkill) orientada a la manipulación determinista del plan.
 * **FR-2.2:** La skill debe exponer tres herramientas clave (*Tools*):
   * create_plan(plan: JSON): Inicializa el grafo de tareas.
   * get_next_executable_tasks(): Retorna una lista de tareas en estado PENDING cuyas dependencias (propiedad dependencies) se encuentren estrictamente en COMPLETED.
   * update_task_status(task_id, status, output_data): Actualiza de forma atómica el estado de una tarea específica.
### 3.3. Ciclo de Vida y Comunicación de Subagentes (A2A)
 * **FR-3.1:** El Coordinador invocará a los subagentes mediante el protocolo de comunicación **Agent-to-Agent (A2A)** provisto por el ADK.
 * **FR-3.2:** La invocación a un subagente debe encapsular únicamente: el task_id, el prompt de la tarea específica y los input_data requeridos. No se enviará el historial completo de la conversación con el cliente.
 * **FR-3.3:** El subagente procesará la petición de manera síncrona/asíncrona en su propio hilo de contexto aislado y devolverá un payload estructurado JSON con el resultado.
### 3.4. Gestión de Errores y Resiliencia (Fallback)
 * **FR-4.1:** Si un subagente retorna un error o la tarea cambia a estado FAILED, el Coordinador debe activar una política de re-planificación (*Replanning*).
 * **FR-4.2:** El Coordinador tendrá un límite de **3 reintentos** automáticos por tarea modificando las instrucciones de entrada. Si el error persiste, el plan global se marcará como FAILED y se notificará al usuario con un mensaje de negocio mitigado (sin stack traces técnicos).
## 4. Requisitos No Funcionales (NFR)
### 4.1. Rendimiento y Escalabilidad
 * **NFR-1.1 (Concurrencia):** El sistema de orquestación debe soportar la ejecución en paralelo de tareas independientes dentro de un mismo plan (ej. si el paso 2 y el paso 3 no tienen dependencias cruzadas, deben enviarse a sus respectivos subagentes en paralelo).
 * **NFR-1.2 (Latencia):** El overhead de procesamiento introducido por la Skill de gestión del plan no debe superar los **150ms** por transición de estado.
### 4.2. Seguridad y Cumplimiento (Compliance)
 * **NFR-2.1 (Trazabilidad - ISO 27001):** Cada mutación de estado del plan (create_plan, update_task_status) debe generar un log estructurado auditable enviado de forma asíncrona a la plataforma de telemetría centralizada.
 * **NFR-2.2 (Privacidad de Datos):** Los datos sensibles del cliente inyectados en el input_data de los subagentes deben sanitizarse o enmascararse si el subagente utiliza un proveedor de LLM externo no corporativo.
## 5. Arquitectura Técnica de Referencia
A nivel de diseño de componentes en el backend, la solución se integrará siguiendo la estructura nativa de herramientas del Google ADK:
```
  ┌────────────────────────────────────────────────────────┐
  │                   COORDINATOR AGENT                    │
  │  - System Prompt: Plan & Execute Workflow              │
  │  - Context: User Chat Session                          │
  └───────────┬────────────────────────────────┬───────────┘
              │                                │
     Utiliza  │                       Invoca   │ via A2A
              ▼                                ▼
  ┌──────────────────────┐          ┌──────────────────────┐
  │ PLAN MANAGEMENT SKILL│          │ SUB-AGENTS (Pool)    │
  │ - create_plan()      │          │ - DataAnalystAgent   │
  │ - get_next_tasks()   │          │ - ReporterAgent      │
  │ - update_status()    │          │ - SQLGeneratorAgent  │
  └───────────┬──────────┘          └───────────┬──────────┘
              │                                │
       Mutación de Estado               Ejecución Aislada
              ▼                                ▼
  ┌────────────────────────────────────────────────────────┐
  │                 PLAN EXECUTION STATE                   │
  │             (Pydantic Object / InMemory / Cache)       │
  └────────────────────────────────────────────────────────┘

```
## 6. Criterios de Aceptación (UAT)
### Escenario 1: Planificación y ejecución exitosa sin dependencias cruzadas
 * **Dado que** un usuario solicita un reporte consolidado que requiere (A) extraer datos de telemetría y (B) auditar políticas de calidad de un archivo de reglas.
 * **Cuando** el Agente Coordinador procesa la solicitud.
 * **Entonces** debe crear un plan con 2 tareas independientes, lanzar ambas ejecuciones a los subagentes en paralelo, actualizar los estados a COMPLETED en el JSON de control y entregar un resumen limpio al usuario.
### Escenario 2: Falla de un Subagente y Recuperación Exitosa
 * **Dado que** un subagente de base de datos falla al ejecutar una consulta debido a un timeout o un error de sintaxis en el SQL generado.
 * **Cuando** el subagente devuelve el error al coordinador.
 * **Entonces** la herramienta update_task_status cambia el estado a FAILED, el Coordinador analiza el error, genera una corrección en las instrucciones de entrada y ejecuta un reintento exitoso, completando finalmente el flujo general del usuario.
## 7. Plan de Lanzamiento y Fases (Milestones)
 * **Fase 1 (PoC):** Implementación de los esquemas Pydantic básicos, la PlanManagementSkill en memoria y simulación de 2 subagentes (Mock). *Duración: 1 semana.*
 * **Fase 2 (Integración):** Conexión con el bus de mensajería A2A de Google ADK y persistencia del estado en base de datos para trazabilidad. *Duración: 2 semanas.*
 * **Fase 3 (Pruebas de Resiliencia y QA):** Inyección de fallos controlados (timeouts, payloads corruptos) para calibrar el prompt de re-planificación del Coordinador. *Duración: 1 semana.*