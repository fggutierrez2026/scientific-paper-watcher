# Plan de Trabajo y Evolución - Scientific Paper Watcher

Plan de desarrollo incremental para evolucionar el repositorio desde la versión actual (`0.3.0`) hacia una plataforma robusta y automatizada de inteligencia científica.

> **Instrucciones de uso:**
> Cada tarea completada se marcará como realizada sustituyendo `- [ ]` por `- [x]`.

---

## Métricas de Progreso Global
- **Fase 0:** 4 / 4 tareas principales completadas (100% completada)
- **Fase 1:** 2 / 4 tareas principales completadas
- **Fase 2:** 0 / 3 tareas principales completadas
- **Fase 3:** 0 / 3 tareas principales completadas
- **Fase 4:** 0 / 3 tareas principales completadas

---

## Fase 0: Estabilización, Calidad y Correcciones Inmediatas (v0.3.1)
**Objetivo:** Eliminar bugs críticos actuales, alinear configuración y establecer una red de seguridad con pruebas automatizadas y CI antes de expandir funcionalidades.

- [x] **Tarea 0.1: Corrección del adaptador de arXiv API**
  - [x] Inspeccionar [`src/paper_watcher/sources/arxiv.py`](file:///home/fernando/Escritorio/my_projects/scientific-paper-watcher/src/paper_watcher/sources/arxiv.py) y eliminar el envoltorio redundante `all:"{query}"` en `search_arxiv` que anula las consultas traducidas por `to_arxiv_query`.
  - [x] Asegurar que `search_query` reciba directamente la cadena traducida sin alterar la sintaxis booleana.
  - [x] Realizar prueba manual de ejecución con queries compuestas (`"protein design"`, `"GBP protein" AND "biological sensor"`) y verificar relevancia de resultados.

- [x] **Tarea 0.2: Corrección y unificación de configuración**
  - [x] Corregir la ruta por defecto de la base de datos en [`src/paper_watcher/config.py`](file:///home/fernando/Escritorio/my_projects/scientific-paper-watcher/src/paper_watcher/config.py) (cambiar `"data/papers.pdb"` a `"data/papers.db"`).
  - [x] Añadir lectura de `NCBI_API_KEY` en `Config` y `load_config()`.
  - [x] Modificar [`src/paper_watcher/sources/pubmed.py`](file:///home/fernando/Escritorio/my_projects/scientific-paper-watcher/src/paper_watcher/sources/pubmed.py) para enviar `api_key` en los parámetros a NCBI cuando esté configurado en `.env`.
  - [x] Unificar los nombres de variables entre `.env`, `.env.example`, `config.py` y la documentación en `README.md` (`PAPER_WATCHER_DB`, `PAPER_WATCHER_REPORT_DIR`, `NCBI_EMAIL`, `NCBI_API_KEY`, `REQUEST_TIMEOUT`, `MAX_RETRIES`).

- [x] **Tarea 0.3: Infraestructura y suite de pruebas automatizadas con `pytest`**
  - [x] Añadir dependencias de test en `pyproject.toml` (o `requirements-dev.txt`): `pytest`, `pytest-mock`.
  - [x] Crear estructura dentro de `tests/`: `conftest.py`, `test_query_language.py`, `test_storage.py`, `test_sources.py`, `test_reports.py`, `test_normalization.py`, `test_config.py`.
  - [x] Implementar tests unitarios para [`src/paper_watcher/query_language.py`](file:///home/fernando/Escritorio/my_projects/scientific-paper-watcher/src/paper_watcher/query_language.py):
    - Tokenización de términos simples, frases entrecomilladas, paréntesis, `+`, `AND`, `OR`, `NOT`.
    - Validación de sintaxis (paréntesis desbalanceados, operadores colgantes, frases vacías).
    - Traducción correcta a sintaxis de PubMed y arXiv.
  - [x] Implementar tests unitarios con mocks/fixtures para [`src/paper_watcher/sources/pubmed.py`](file:///home/fernando/Escritorio/my_projects/scientific-paper-watcher/src/paper_watcher/sources/pubmed.py) (parseo XML de artículos reales, autores, fechas, DOI).
  - [x] Implementar tests unitarios con mocks/fixtures para [`src/paper_watcher/sources/arxiv.py`](file:///home/fernando/Escritorio/my_projects/scientific-paper-watcher/src/paper_watcher/sources/arxiv.py) (parseo XML Atom, extracción de ID, throttling).
  - [x] Implementar tests para [`src/paper_watcher/storage/sqlite.py`](file:///home/fernando/Escritorio/my_projects/scientific-paper-watcher/src/paper_watcher/storage/sqlite.py) (inicialización de tablas, inserción idempotente, cálculo de nuevos vs conocidos, registro de procedencia).

- [x] **Tarea 0.4: Pipeline de Integración Continua (CI)**
  - [x] Crear workflow en `.github/workflows/ci.yml`.
  - [x] Configurar ejecución automática de `pytest`, chequeo de formato/linting con `ruff` y análisis de tipos con `mypy` en cada push o pull request.

---

## Fase 1: Deduplicación Cross-Source, Nuevas Fuentes y Ventanas Temporales (v0.4.0)
**Objetivo:** Garantizar que la recopilación científica sea completa, sin duplicados entre preprints y revistas indexadas, y con capacidad de búsqueda incremental.

- [x] **Tarea 1.1: Deduplicación y fusión cross-source (Resolución por DOI / Título)**
  - [x] Analizar y rediseñar el esquema de base de datos para permitir que una misma publicación canónica vincule múltiples fuentes (ej. versión arXiv y posterior versión PubMed).
  - [x] Implementar algoritmo de fusión: si un paper entrante coincide en DOI o título normalizado con uno existente, asociar la nueva fuente/URL sin duplicar la entidad.
  - [x] Actualizar los reportes Markdown para indicar si un paper fue avistado tanto en preprint como en revista revisada por pares.

- [x] **Tarea 1.2: Integración de fuentes bioRxiv y medRxiv**
  - [x] Crear [`src/paper_watcher/sources/biorxiv.py`](file:///home/fernando/Escritorio/my_projects/scientific-paper-watcher/src/paper_watcher/sources/biorxiv.py) usando la API de bioRxiv/medRxiv.
  - [x] Mapear respuestas al modelo común `Paper`.
  - [x] Integrar bioRxiv al pipeline de búsqueda en `main.py` manteniendo aislamiento de fallos.
  - [x] Añadir tests correspondientes en `tests/test_sources.py`.

- [ ] **Tarea 1.3: Integración de OpenAlex / Europe PMC**
  - [ ] Diseñar adaptador para OpenAlex (`sources/openalex.py`) para enriquecer papers con citas, tópicos y enlaces open-access a PDFs completos.
  - [ ] Configurar llamadas opcionales controladas por flags o variables de entorno.

- [ ] **Tarea 1.4: Búsquedas incrementales y ventanas de tiempo**
  - [ ] Agregar columna `last_checked_at` en la tabla `watch_queries`.
  - [ ] Añadir flag de CLI: `--since` / `--days N` en el comando `paper-watcher run`.
  - [ ] Modificar adaptadores de fuentes para filtrar por rango de fechas (ej. `mindate`/`maxdate` en PubMed, `submittedDate` en arXiv) y traer solo novedades efectivas.

---

## Fase 2: Automatización, Alertas y Exportación Académica (v0.5.0)
**Objetivo:** Desatender la ejecución manual mediante servicios programados, despachar alertas instantáneas y permitir interoperabilidad con gestores bibliográficos.

- [ ] **Tarea 2.1: Exportadores académicos (BibTeX, JSON, CSV)**
  - [ ] Crear módulo [`src/paper_watcher/reports/bibtex.py`](file:///home/fernando/Escritorio/my_projects/scientific-paper-watcher/src/paper_watcher/reports/bibtex.py) para exportar colecciones en formato `.bib` (compatible con Zotero, Mendeley, Overleaf y LaTeX).
  - [ ] Añadir exportador estructurado a JSON y CSV/TSV.
  - [ ] Incorporar comandos CLI: `paper-watcher export --format bibtex|json|csv`.

- [ ] **Tarea 2.2: Sistema de notificaciones multicanal (Alertas)**
  - [ ] Crear paquete `src/paper_watcher/notifiers/` con interfaz abstracta `BaseNotifier`.
  - [ ] Implementar `WebhookNotifier` para publicar resúmenes de nuevos papers en Slack y Discord.
  - [ ] Implementar `TelegramNotifier` para envío de resúmenes directos vía bot de Telegram.
  - [ ] Implementar `EmailDigestNotifier` para enviar resúmenes periódicos vía SMTP.
  - [ ] Configurar habilitación de notificaciones desde `.env`.

- [ ] **Tarea 2.3: Automatización en segundo plano (Daemon / Cron / Docker)**
  - [ ] Crear plantillas `systemd`: `paper-watcher.service` y `paper-watcher.timer` para ejecución diaria automática en Linux.
  - [ ] Crear `Dockerfile` y `docker-compose.yml` para despliegue aislado y portable.
  - [ ] Documentar en `README.md` la puesta en marcha del servicio desatendido y visualización de logs con `journalctl`.

---

## Fase 3: Inteligencia de Contenido y Relevancia con IA (v0.6.0)
**Objetivo:** Reducir la sobrecarga cognitiva del investigador mediante filtrado por relevancia y síntesis automática de artículos.

- [ ] **Tarea 3.1: Resúmenes sintéticos ejecutivos (TL;DR)**
  - [ ] Crear módulo `src/paper_watcher/ai/` con cliente modular (soporte Ollama para inferencia local y API de Gemini/OpenAI como alternativa).
  - [ ] Generar síntesis estructurada de 3 puntos: Objetivo, Metodología y Conclusión principal.
  - [ ] Persistir el resumen en la base de datos e integrarlo en los reportes Markdown y alertas.

- [ ] **Tarea 3.2: Puntuación de relevancia contextual (Scoring)**
  - [ ] Permitir al usuario definir un archivo de perfil de investigación (`interests.yaml` o palabras clave con peso).
  - [ ] Implementar algoritmo de scoring (0 a 100) basado en keywords o embeddings de similitud semántica.
  - [ ] Filtrar o destacar papers con alta relevancia en los reportes.

- [ ] **Tarea 3.3: Extracción automática de entidades científicas**
  - [ ] Extraer automáticamente genes/proteínas (mapeables a UniProt), organismos modelo y métodos experimentales citados en el abstract.
  - [ ] Almacenar etiquetas de entidades para facilitar búsquedas avanzadas dentro del repositorio local.

---

## Fase 4: Experiencia de Usuario, TUI y Web Dashboard (v1.0.0)
**Objetivo:** Ofrecer interfaces visuales ricas para navegar la biblioteca de artículos recopilados y gestionar el flujo de lectura.

- [ ] **Tarea 4.1: Flujo de lectura en base de datos**
  - [ ] Extender tabla `papers` con campos: `is_read`, `is_starred`, `notes`.
  - [ ] Crear comandos CLI para gestionar estado: `paper-watcher mark-read <id>`, `paper-watcher star <id>`.

- [ ] **Tarea 4.2: TUI (Terminal User Interface)**
  - [ ] Desarrollar una interfaz de terminal con `Textual` para explorar artículos, leer abstracts con formateo rico, filtrar por query/fecha y marcar lecturas directamente desde la consola.

- [ ] **Tarea 4.3: Dashboard Web ligero (FastAPI / Streamlit)**
  - [ ] Crear visualizador web para gráficos de evolución de publicaciones por tema en el tiempo.
  - [ ] Buscador interactivo sobre la base de datos local de papers.