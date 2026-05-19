
# DOCUMENTO DE REQUISITOS DEL PRODUCTO (PRD)

## Sistema Agéntica General basado en Skills Distribuidos

**Autor:** Ilver Anache

**Estatus:** Listo para Desarrollo (Base para Gemini Code Assist / GSD Framework)

**Stack Tecnológico Core:** Google AI ADK, GitHub (SSOT), Anthropic Tool Standard (JSON Schema), uv and Python 3.11 (FastAPI), Deno Sandbox, WebAssembly (Extism).

---

## 1. Visión General del Producto

### 1.1. Declaración del Problema

Las soluciones agénticas tradicionales sufren de rigidez arquitectónica. Añadir nuevas capacidades o adaptar el sistema a diferentes escenarios empresariales (QA, Scrum, DevOps, Analítica) suele requerir la reconfiguración del Agente Central, el reentrenamiento de modelos o el despliegue continuo de código base, incrementando los costos operativos y el riesgo de regresiones en entornos de misión crítica.

### 1.2. Solución del Producto

Una plataforma agéntica desacoplada y dinámicamente extensible basada en el framework **Google AI ADK**. El sistema centraliza el descubrimiento de capacidades a través de un archivo ligero de catálogo raíz (`catalog.yaml`) alojado en GitHub. La lógica técnica detallada y los esquemas de parámetros se delegan de forma distribuida a la carpeta de cada skill utilizando el **estándar de herramientas de Anthropic (`skill.json`)** y documentación funcional (`SKILL.md`). El sistema implementa un patrón híbrido de descubrimiento para buscar en caliente e inyectar habilidades en tiempo de ejecución de forma segura, ligera y auditada mediante Sandboxing.

---

## 2. Arquitectura del Catálogo Distribuido (GitHub SSOT)

El repositorio central actúa como la única fuente de verdad (SSOT). La estructura está dividida en dos niveles para maximizar el rendimiento de la IA y minimizar el consumo de tokens en llamadas concurrentes (https://github.com/ianache/skills-catalog)

### 2.1. Nivel 1: Manifiesto Ligero Raíz (`catalog.yaml`)

Ubicado en la raíz del repositorio, contiene exclusivamente metadatos de descubrimiento de primer nivel y etiquetas analíticas para permitir el filtrado por código nativo en memoria.

```yaml
version: "2.0"
namespace: "comsatel.agente.core"
updated_at: "2026-05-16T12:30:00Z"

skills:
  - name: evaluar-test-case
    description: Skill dedicado a evaluar la calidad y completitud de especificaciones de casos de prueba.
    path: "skills/evaluar_test_case"
    status: active
    tags: ["qa", "testing", "calidad", "review"]

  - name: especificar_user_story
    description: Especificar historias de usuario basadas en metodologia SCRUM.
    path: "skills/especificar_user_story"
    status: active
    tags: ["scrum", "agile", "user-story", "requisitos"]

  - name: especificar_testcase
    description: Especificar casos de prueba basados en metodologia SCRUM.
    path: "skills/especificar_testcase"
    status: active
    tags: ["scrum", "qa", "testing", "casos-prueba"]

  - name: software_realiability_engineering
    description: Evaluar la confiabilidad de un sistema de software.
    path: "skills/software_realiability_engineering"
    status: active
    tags: ["sre", "devops", "reliability", "infrastructure"]

  - name: calculator
    description: Skill dedicado a realizar operaciones matemáticas básicas.
    path: "skills/calculator"
    status: active
    tags: ["utility", "math", "calculator"]

  - name: qdrant_kb
    description: Gestión de base de conocimientos vectorial en Qdrant (mykb) para almacenamiento y búsqueda semántica.
    path: "skills/qdrant_kb"
    status: active
    tags: ["qdrant", "vector-db", "mykb", "rag"]

  - name: gitlab_manager
    description: Skill para gestionar grupos, usuarios e issues en GitLab.
    path: "skills/gitlab_manager"
    status: active
    tags: ["gitlab", "devops", "issues", "git"]

```

### 2.2. Nivel 2: Estructura de la Carpeta del Skill (Lazy Loading)

Cada habilidad mapeada en el `path` del catálogo debe contar obligatoriamente con los siguientes archivos independientes dentro de su subdirectorio:

1. **`skill.json`**: Estructura técnica formal siguiendo el estándar de herramientas de Anthropic (*Anthropic Tool Definition Schema*). Define los contratos de entrada requeridos por el LLM.
2. **`SKILL.md`**: Guía cognitiva y de gobernanza en lenguaje natural, restricciones de negocio corporativo y ejemplos de pocas oportunidades (*few-shot prompting*).

---

## 3. Requisitos Funcionales y Flujos Agénticos (Core AI ADK)

### 3.1. Patrón Híbrido de Descubrimiento de Capacidades

El sistema operará bajo una estrategia de caché indexada localmente. En caso de fallas de coincidencia semántica, se activará el siguiente algoritmo asíncrono:

* **REQ-01 (Umbral de Confianza):** Si el *Coordinating Agent* calcula un score de confianza inferior a `0.72` en su base local, interceptará el flujo y delegará la tarea al sub-agente *Catalog Explorer Agent*.
* **REQ-02 (Extracción de Tags):** El sistema extraerá cognitivamente de la petición del usuario de 1 a 3 tags de TI/Negocio (ej: `"gitlab"`, `"testing"`).
* **REQ-03 (Pre-filtrado Programático):** El *Catalog Explorer Agent* consumirá la API de contenidos de GitHub para descargar el `catalog.yaml` crudo. Descartará mediante código nativo en memoria todo nodo de skill cuya intersección de tags con la petición sea vacía.
* **REQ-04 (Lazy Loading Contract):** Al identificar los skills idóneos mediante los tags, el agente resolverá el `path` respectivo y descargará únicamente el `skill.json`. Este JSON Schema se inyectará dinámicamente en caliente al contexto de herramientas activas del *Coordinating Agent* para procesar la transacción actual.
* **REQ-05 (Auto-Curación de Caché):** Tras completar una ejecución exitosa de un skill descubierto en caliente, el sistema indexará asíncronamente sus metadatos en la caché vectorial local del orquestador para mitigar la latencia en consultas subsiguientes.

### 3.2. Flujo Multi-Escenario Secuencial (Orquestación Cross-Domain)

* **REQ-06 (Encadenamiento Dinámico - Grafo de Ejecución DAG):** El Agente Coordinador debe tener la capacidad cognitiva de orquestar flujos de trabajo multi-skill secuenciales basándose en un único prompt amplio del usuario.
* *Caso de Uso Tipo:* "Refinar requerimiento de negocio".
1. El Coordinador activa el skill `especificar_user_story` para estructurar la especificación en formato SCRUM ágil.
2. Pasa el output como input para el skill `especificar_testcase` para generar casos de prueba técnicos.
3. Ejecuta el skill `evaluar-test-case` para auditar la cobertura de límites y criterios de aceptación.
4. Consolida la documentación usando `qdrant_kb` (*mykb*) y abre las tareas de desarrollo correspondientes a través de `gitlab_manager`.



---

## 4. Requisitos No Funcionales y Motor de Ejecución (Execution Engine)

### 4.1. Seguridad y Modos de Ejecución (Tooling Channels)

El motor de ejecución tomará el payload validado del LLM y lo procesará bajo tres canales estrictamente regulados según el skill:

* **Canal WebAssembly Sandbox (Cómputo):** Obligatorio para ejecuciones de código dinámico cerrado y cálculos utilitarios matemáticos (`calculator`). Correrá usando el runtime `Extism/Wasmtime` dentro del mismo proceso Python con latencias de arranque en microsegundos, sin acceso a red y con memoria completamente aislada.
* **Canal Deno Sandbox (I/O & APIs):** Entorno seguro por defecto para procesamiento de scripts TypeScript/JavaScript (`evaluar-test-case`, `especificar_user_story`). Se invoca mediante subprocesos usando flags estrictos de red granular (`--allow-net=gitlab.com`), denegación de lectura/escritura de archivos y aislamiento V8 con timeouts innegociables de 5000ms.
* **Canal MCP (Model Context Protocol):** Integración nativa bidireccional para bases de datos relacionales y vectoriales corporativas (`qdrant_kb`). Las solicitudes se serializarán en llamadas de procedimiento remoto (RPC) seguras bajo el protocolo MCP.
* **Canal Docker (Evolución Futura):** Preparado arquitectónicamente para añadir ejecución de contenedores efímeros aislados en el clúster Oracle OKE cuando se requieran herramientas complejas del sistema operativo o scripts SRE pesados.

### 4.2. Métricas y Gobernanza (Execution Logs)

* **REQ-07 (Inmutabilidad de Logs):** Cada ciclo de vida agéntico (Mensaje inicial $\rightarrow$ Extracción de Tags $\rightarrow$ Carga dinámica de Skill $\rightarrow$ Parámetros validados $\rightarrow$ Output del canal de ejecución) debe persistirse de forma íntegra e inmutable para la alineación con normativas ISO 27001 / BASC.
* **REQ-08 (Freno de Mano Agéntico):** El motor de ejecución interceptará el payload generado por el LLM y lo contrastará con el `input_schema` del skill antes de disparar cualquier acción. Si falta un parámetro obligatorio, bloqueará la llamada a la infraestructura y solicitará la corrección del payload al agente de forma interna.

---

## 5. Matriz de Criterios de Aceptación Técnicos

| ID | Escenario de Prueba | Condición de Entrada | Comportamiento Esperado | Criterio de Éxito GSD |
| --- | --- | --- | --- | --- |
| **TC-01** | Descubrimiento Exitoso On-Demand | Se publica un skill en GitHub. El Coordinador local no lo tiene en caché. | El coordinador calcula score bajo local. Llama al Explorer Agent, pre-filtra por tags en memoria, descarga `skill.json` e inyecta la herramienta. | Ejecución limpia del sub-agente correspondiente. Latencia agregada por fallback $< 2.5$ segundos. |
| **TC-02** | Validación Estricta de Parámetros | El LLM extrae los parámetros de la solicitud para interactuar con `gitlab_manager`. | El motor de ejecución intercepta el payload y lo contrasta contra el JSON Schema de `skill.json`. | Si falta un parámetro obligatorio (`project_id`), bloquea la ejecución, no llama a la API e instruye al agente a solicitar la información faltante. |
| **TC-03** | Mitigación de Bucles en Sandbox | Un script de TypeScript en Deno genera un bucle infinito o un desborde de memoria. | El motor de ejecución dispara el script dentro del proceso de Deno con aislamiento. | El orquestador mata el proceso al alcanzar el timeout estricto de 5000ms, limpia los recursos efímeros y retorna un error controlado al log sin degradar el core. |
