# Plan de Trabajo y Evolución - Scientific Paper Watcher

Plan de desarrollo incremental para evolucionar el repositorio desde la versión actual (`0.4.0`) hacia un buscador unificado de papers y patentes, con recuperación multi-API y filtrado semántico de relevancia.

> **Instrucciones de uso:**
> Cada tarea completada se marcará como realizada sustituyendo `- [ ]` por `- [x]`.

---

## Métricas de Progreso Global

- **Fase 0:** 4 / 4 tareas principales completadas (100% completada)
- **Fase 1:** 4 / 4 tareas principales completadas (100% completada)
- **Fase 2:** 3 / 4 tareas principales completadas (75% completada)
- **Fase 3:** 0 / 6 tareas principales completadas
- **Fase 4:** 0 / 5 tareas principales completadas
- **Fase 5:** 0 / 5 tareas principales completadas
- **Fase 6:** 0 / 3 tareas principales completadas

---

## Decisiones de producto y alcance

- El ámbito de búsqueda se representará con `papers`, `patents` y `all`.
- El ámbito predeterminado será **`papers`**.
- Se añadirá el comando explícito `paper-watcher search`; `run` conservará compatibilidad y seguirá ejecutando consultas vigiladas.
- Una consulta vigilada almacenará su ámbito para que las ejecuciones incrementales sean reproducibles.
- Papers y documentos de patente tendrán modelos y tablas separados. Los miembros de una misma familia de patentes se vincularán, pero no se fusionarán como si fueran el mismo documento jurídico.
- Unpaywall actuará principalmente como enriquecedor de acceso abierto por DOI, no como fuente primaria equivalente a PubMed o Crossref.
- El filtrado semántico se activará inicialmente de forma optativa y solo pasará a ser predeterminado después de cumplir los criterios de precisión y recall definidos en la fase 5.
- No se hará scraping para sustituir APIs restringidas. Las fuentes sin credenciales o licencia quedarán deshabilitadas con un diagnóstico accionable.

## Protocolo de cierre obligatorio para cada tarea

Cada tarea principal de las fases 2–6 terminará con estas subtareas:

1. Ejecutar `ruff check src tests`, `mypy src tests`, `pytest` y `git diff --check`.
2. Actualizar `.env.example`, `README.md` y este plan cuando cambien configuración, CLI o estado de avance.
3. Verificar que fixtures, logs y commits no contienen tokens, correos privados ni secretos.
4. Crear un commit atómico con el mensaje sugerido en la tarea.
5. Subir la rama y el commit a GitHub mediante `git push origin <rama>`.

## Restricciones de acceso verificadas antes de implementar

| API | Rol previsto | Acceso que debe contemplar el diseño |
|---|---|---|
| Semantic Scholar | Descubrimiento y enriquecimiento de papers | Academic Graph API; clave opcional/recomendada en `x-api-key`; su búsqueda de relevancia no acepta la sintaxis booleana común. |
| Crossref | Descubrimiento y metadatos DOI | API pública; usar `mailto`, `User-Agent`, caché, paginación por cursor y filtros temporales. |
| CORE | Papers y texto completo open-access | Registro y API key requeridos; validar licencia/cuota antes de habilitar por defecto. |
| Unpaywall | Estado OA y mejor ubicación por DOI | Requiere correo en cada solicitud; soporta DOI y búsqueda de títulos, pero se priorizará el enriquecimiento. |
| The Lens | Papers, patentes y vínculos de citación | Token y aprobación previa; puede requerir plan institucional, atribución y renovación. |
| USPTO / PatentsView | Patentes estadounidenses | `X-Api-Key` y límites de uso; confirmar disponibilidad de nuevas claves y transición al Open Data Portal antes de codificar. |
| EPO OPS | Patentes y familias internacionales | Registro, aplicación y OAuth; respetar cuotas y respuestas XML. |
| WIPO PATENTSCOPE | Solicitudes PCT | El webservice es SOAP y de acceso condicional; confirmar contrato, funciones de búsqueda y coste antes de habilitarlo. |

Fuentes oficiales para revalidar durante la implementación:

- [Semantic Scholar Academic Graph API](https://api.semanticscholar.org/api-docs)
- [Crossref REST API](https://www.crossref.org/documentation/retrieve-metadata/rest-api/)
- [CORE API](https://core.ac.uk/services/api)
- [Unpaywall REST API](https://data.unpaywall.org/products/api)
- [The Lens API](https://docs.api.lens.org/)
- [USPTO PatentsView PatentSearch API](https://search.patentsview.org/docs/docs/Search%20API/SearchAPIReference/)
- [EPO Open Patent Services](https://www.epo.org/en/searching-for-patents/data/web-services/ops)
- [WIPO PCT Data Products and Services](https://www.wipo.int/en/web/patentscope/data/index)

---

## Fase 2: Fundaciones de dominio y enrutamiento (v0.5.0)

**Objetivo:** Preparar una arquitectura que pueda buscar papers, patentes o ambos sin romper el comportamiento existente.

- [x] **Tarea 2.1: Matriz de acceso, configuración y seguridad de APIs**
  - [x] Crear `docs/api-access.md` con endpoint, propietario, alta, licencia, cuota, paginación, filtro temporal, campos disponibles y estado (`ready`, `credentials-required`, `blocked`) de cada API.
  - [x] Definir variables: `SEMANTIC_SCHOLAR_API_KEY`, `CROSSREF_EMAIL`, `CORE_API_KEY`, `UNPAYWALL_EMAIL`, `LENS_API_TOKEN`, `USPTO_API_KEY`, `EPO_CONSUMER_KEY`, `EPO_CONSUMER_SECRET` y las credenciales WIPO que autorice su contrato.
  - [x] Implementar lectura segura de credenciales, validación solo al activar la fuente y mensajes que expliquen cómo obtener acceso sin imprimir secretos.
  - [x] Añadir una política de fuentes habilitadas (`PAPER_SOURCES`, `PATENT_SOURCES`) para que una API restringida no bloquee las demás.
  - [x] Añadir pruebas de configuración, credencial ausente, token redactado y fuente deshabilitada.
  - [x] Cerrar con commit sugerido `chore: define external API access and configuration` y push a GitHub.

- [x] **Tarea 2.2: Modelo canónico y persistencia de patentes**
  - [x] Crear `Patent` con número de publicación, número de solicitud, jurisdicción, título, abstract, inventores, solicitantes, fechas de prioridad/publicación, CPC/IPC, familia, citas, URL y procedencia.
  - [x] Crear mediante migración aditiva las tablas `patents`, `patent_sources`, `patent_query_matches` y `patent_families` sin alterar los papers existentes.
  - [x] Definir identidad por `jurisdiction + publication_number`; usar `application_number` como respaldo y vincular miembros mediante `family_id` sin fusionarlos.
  - [x] Añadir tabla `paper_patent_links` para relaciones de citación provenientes de Lens u otras fuentes verificables.
  - [x] Implementar inserción idempotente, fusión de metadatos y trazabilidad de todas las fuentes.
  - [x] Añadir migraciones y pruebas de deduplicación, familias, procedencia y compatibilidad con bases `v0.4.0`.
  - [x] Cerrar con commit sugerido `feat: add canonical patent storage model` y push a GitHub.

- [x] **Tarea 2.3: Contrato común de adaptadores y orquestador por ámbito**
  - [x] Definir un protocolo de adaptador con capacidades (`paper`, `patent`, `discovery`, `enrichment`, filtros temporales y paginación).
  - [x] Crear registros separados de fuentes para papers y patentes, con orden estable y selección configurable.
  - [x] Normalizar resultados en `Paper` o `Patent` y devolver conteos, cursor, truncamiento, advertencias y estado de la fuente.
  - [x] Reutilizar timeouts, reintentos, `Retry-After`, redacción de credenciales y aislamiento de fallos en un cliente HTTP común sin eliminar particularidades de cada proveedor.
  - [x] Impedir llamadas duplicadas a Lens en el modo `all` coordinando sus endpoints scholarly y patent.
  - [x] Añadir pruebas contractuales reutilizables que todo adaptador deba superar.
  - [x] Cerrar con commit sugerido `refactor: add scoped source adapter registry` y push a GitHub.

- [ ] **Tarea 2.4: Comando de búsqueda y ámbito predeterminado `papers`**
  - [ ] Añadir `paper-watcher search --query QUERY --scope papers|patents|all`, con `papers` como valor predeterminado.
  - [ ] Mantener `paper-watcher run --query` como alias compatible durante al menos una versión y documentar su futura evolución.
  - [ ] Añadir `--scope` a `add-query` y `run`; migrar consultas existentes con `scope='papers'` y mostrarlo en `list-queries`.
  - [ ] Enrutar `papers` solo al registro científico, `patents` solo al registro de patentes y `all` a ambos.
  - [ ] Generar secciones separadas en consola y Markdown, además de conteos por tipo documental.
  - [ ] Añadir pruebas CLI de valor predeterminado, los tres ámbitos, argumentos inválidos y compatibilidad hacia atrás.
  - [ ] Cerrar con commit sugerido `feat: add scoped paper and patent search command` y push a GitHub.

---

## Fase 3: Nuevas APIs de papers (v0.6.0)

**Objetivo:** Ampliar cobertura científica sin multiplicar duplicados ni convertir enriquecedores en fuentes de descubrimiento indiscriminadas.

- [ ] **Tarea 3.1: Adaptador Semantic Scholar**
  - [ ] Implementar búsqueda paginada con campos explícitos para ID, DOI, PMID, arXiv ID, título, abstract, autores, venue, fechas, citas, tópicos y PDF OA.
  - [ ] Crear una traducción documentada desde la consulta común a texto plano, ya que el endpoint de relevancia no soporta operadores booleanos.
  - [ ] Implementar filtros de fecha, límites, `x-api-key`, `429` y reintentos respetando `Retry-After`.
  - [ ] Mapear identificadores para deduplicar contra PubMed, arXiv, Crossref y OpenAlex.
  - [ ] Añadir fixtures JSON, pruebas de parseo, paginación, fechas, errores y aislamiento.
  - [ ] Cerrar con commit sugerido `feat: integrate Semantic Scholar paper search` y push a GitHub.

- [ ] **Tarea 3.2: Adaptador Crossref**
  - [ ] Implementar `/works` con `query.bibliographic`, `select`, cursor y filtros `from-update-date`/`until-update-date` para búsquedas incrementales.
  - [ ] Enviar `mailto` y un `User-Agent` identificable; añadir soporte opcional para token Metadata Plus sin exigirlo.
  - [ ] Parsear DOI, títulos, autores, abstract, fechas, tipo, editorial, referencias, licencias y enlaces de recursos.
  - [ ] Sanear abstracts JATS/HTML y registrar ausencia de abstract sin inventar contenido.
  - [ ] Añadir pruebas para cursores, rate limits, fechas parciales, HTML y respuestas incompletas.
  - [ ] Cerrar con commit sugerido `feat: integrate Crossref works search` y push a GitHub.

- [ ] **Tarea 3.3: Adaptador CORE**
  - [ ] Confirmar la licencia y cuota concedidas a la API key antes de implementar llamadas en producción.
  - [ ] Implementar búsqueda paginada y mapeo de DOI, repositorio, autores, abstract, texto completo y URL de descarga permitida.
  - [ ] Incorporar filtros temporales nativos o filtrado local explícito cuando el contrato de la API no ofrezca equivalencia.
  - [ ] Evitar descargar full text durante búsquedas normales; hacerlo solo bajo una opción separada y con caché.
  - [ ] Añadir pruebas de autenticación, cuota, paginación, metadatos sin DOI y licencia de descarga.
  - [ ] Cerrar con commit sugerido `feat: integrate CORE paper search` y push a GitHub.

- [ ] **Tarea 3.4: Enriquecimiento Unpaywall**
  - [ ] Crear un enriquecedor por DOI que recupere estado OA, licencia, versión y mejor ubicación/PDF.
  - [ ] Reutilizar `NCBI_EMAIL` solo mediante decisión explícita o exigir `UNPAYWALL_EMAIL`; nunca enviar un correo vacío.
  - [ ] Aplicar caché por DOI y fecha de actualización para no repetir consultas en cada ejecución.
  - [ ] Definir precedencia entre PDF de OpenAlex, CORE, Unpaywall y la fuente original, conservando todas las URLs y su procedencia.
  - [ ] Mantener la búsqueda por título de Unpaywall como capacidad optativa, deshabilitada por defecto para reducir duplicados.
  - [ ] Añadir pruebas de DOI inexistente, OA cerrado, múltiples ubicaciones, rate limit y caché.
  - [ ] Cerrar con commit sugerido `feat: add Unpaywall open access enrichment` y push a GitHub.

- [ ] **Tarea 3.5: Adaptador scholarly de The Lens**
  - [ ] Bloquear la implementación en vivo hasta disponer de aprobación, token y condiciones de atribución documentadas; desarrollar mientras tanto contra fixtures contractuales.
  - [ ] Implementar POST de búsqueda, selección de campos, orden, cursor/scroll y redacción del bearer token.
  - [ ] Mapear DOI, PMID, identificadores, citas científicas y conteo/enlaces de citas desde patentes.
  - [ ] Incorporar la atribución exigida en reportes y documentación cuando Lens esté habilitado.
  - [ ] Añadir pruebas de token ausente/expirado, `204`, scroll expirado, cuota y transformación.
  - [ ] Cerrar con commit sugerido `feat: integrate Lens scholarly search` y push a GitHub.

- [ ] **Tarea 3.6: Fusión multi-API de papers**
  - [ ] Extender `paper_sources` para conservar todos los identificadores y URLs de Semantic Scholar, Crossref, CORE, Unpaywall y Lens.
  - [ ] Definir precedencia campo a campo: identidad, título, abstract, fecha, autores, citas, tópicos, licencia y PDF.
  - [ ] Separar métricas dinámicas, como citas, de metadatos estables y guardar `last_enriched_at`.
  - [ ] Evitar que un enriquecedor incremente el conteo de fuentes de descubrimiento o genere por sí solo un “paper nuevo”.
  - [ ] Añadir pruebas end-to-end con un mismo DOI presente en cinco APIs y variantes de título sin DOI.
  - [ ] Cerrar con commit sugerido `feat: merge multi-api scholarly metadata` y push a GitHub.

---

## Fase 4: APIs y normalización de patentes (v0.7.0)

**Objetivo:** Buscar patentes estadounidenses, europeas e internacionales, preservando documentos, familias, clasificaciones y vínculos con papers.

- [ ] **Tarea 4.1: Adaptador USPTO / PatentsView**
  - [ ] Realizar un spike contra PatentsView y el USPTO Open Data Portal para escoger el endpoint que permita búsqueda textual reproducible de grants y pre-grants.
  - [ ] Confirmar que existe una API key utilizable; si nuevas altas siguen suspendidas, mantener el adaptador como `credentials-required` sin bloquear otras fuentes.
  - [ ] Implementar `X-Api-Key`, consulta, campos, orden, paginación y límite de 45 solicitudes/minuto según el contrato vigente.
  - [ ] Mapear grants y solicitudes pre-grant, inventores, assignees, fechas, CPC/IPC, citas, claims/abstract disponibles y URLs oficiales.
  - [ ] Añadir pruebas de ambos tipos documentales, rate limit, `Retry-After`, paginación y números normalizados.
  - [ ] Cerrar con commit sugerido `feat: integrate USPTO patent search` y push a GitHub.

- [ ] **Tarea 4.2: Adaptador EPO OPS**
  - [ ] Registrar una aplicación de prueba y documentar el flujo OAuth con `EPO_CONSUMER_KEY` y `EPO_CONSUMER_SECRET`.
  - [ ] Implementar búsqueda CQL, token cacheado, renovación, cuotas, backoff y parsing XML con namespaces.
  - [ ] Recuperar bibliografía, abstract, prioridad, solicitantes, inventores, CPC/IPC, familia INPADOC y eventos legales permitidos.
  - [ ] Traducir la consulta común a una expresión CQL segura, escapando términos y frases.
  - [ ] Añadir fixtures XML y pruebas de OAuth, token vencido, cuotas, familias, idiomas y respuestas parciales.
  - [ ] Cerrar con commit sugerido `feat: integrate EPO OPS patent search` y push a GitHub.

- [ ] **Tarea 4.3: Integración WIPO PATENTSCOPE condicionada por acceso**
  - [ ] Solicitar/confirmar acceso al PCT Webservice y verificar por escrito que el contrato incluye búsqueda de registros, no solo descarga de documentos.
  - [ ] Documentar coste, restricciones de redistribución, atribución y tipos de documento autorizados.
  - [ ] Si se concede acceso adecuado, aislar el cliente SOAP detrás del protocolo de adaptadores y mapear publicaciones PCT, idiomas, prioridades y documentos.
  - [ ] Si el acceso no permite búsqueda, entregar un adaptador deshabilitado con diagnóstico y una ADR que explique el bloqueo; no automatizar PATENTSCOPE web.
  - [ ] Añadir pruebas contractuales con respuestas autorizadas y pruebas del comportamiento bloqueado sin credenciales.
  - [ ] Cerrar con commit sugerido `feat: add gated WIPO PATENTSCOPE integration` y push a GitHub.

- [ ] **Tarea 4.4: Adaptador de patentes de The Lens**
  - [ ] Reutilizar el acceso, cliente y atribución de Lens sin compartir accidentalmente tokens entre logs o URLs.
  - [ ] Implementar búsqueda de patentes con selección de campos, relevancia, fechas, cursor y manejo de expiración.
  - [ ] Mapear familias, jurisdicción, solicitantes, inventores, clasificaciones, citas de patentes y citas a trabajos científicos.
  - [ ] Poblar `paper_patent_links` solo cuando Lens entregue una relación explícita y conservar su procedencia.
  - [ ] Añadir pruebas de vínculos paper-patente, scroll, `204`, cuotas y duplicados con USPTO/EPO/WIPO.
  - [ ] Cerrar con commit sugerido `feat: integrate Lens patent search and citations` y push a GitHub.

- [ ] **Tarea 4.5: Deduplicación y reportes de patentes**
  - [ ] Normalizar números DOCDB/EPODOC, códigos de país, kind codes, números PCT y clasificaciones CPC/IPC.
  - [ ] Resolver duplicados del mismo documento entre Lens, USPTO, EPO y WIPO sin colapsar miembros distintos de una familia.
  - [ ] Crear reportes Markdown separados para patentes y una vista combinada con vínculos paper-patente.
  - [ ] Mostrar fuente, jurisdicción, estado/fase, familia, prioridad, solicitante, inventores, abstract, clasificaciones y URL.
  - [ ] Añadir fixtures cruzados y pruebas de identidad, familias, procedencia y renderizado seguro.
  - [ ] Cerrar con commit sugerido `feat: add patent deduplication and reports` y push a GitHub.

---

## Fase 5: Filtrado semántico de falsos positivos (v0.8.0)

**Objetivo:** Mejorar la precisión de resultados usando título y abstract sin descartar silenciosamente trabajos relevantes.

- [ ] **Tarea 5.1: Dataset de evaluación y línea base**
  - [ ] Recopilar resultados reales de papers y patentes para varias consultas representativas, eliminando datos sensibles y respetando licencias.
  - [ ] Etiquetar manualmente cada resultado como relevante, dudoso o falso positivo y versionar únicamente fixtures redistribuibles.
  - [ ] Medir la línea base léxica: precisión, recall, F1, precisión@N y falsos positivos por fuente y por ámbito.
  - [ ] Definir criterio de aceptación: mejorar precisión frente a la línea base manteniendo al menos 90% de recall sobre los positivos etiquetados.
  - [ ] Añadir `docs/semantic-evaluation.md` con protocolo reproducible y resultados iniciales.
  - [ ] Cerrar con commit sugerido `test: add semantic relevance benchmark` y push a GitHub.

- [ ] **Tarea 5.2: Intención semántica y contrato de scoring**
  - [ ] Añadir `semantic_intent` opcional a consultas vigiladas para expresar en lenguaje natural qué resultados interesan, separado de la sintaxis booleana.
  - [ ] Añadir `--intent TEXT` a `search` y `add-query`; usar una conversión determinista de la query solo cuando no exista intención explícita.
  - [ ] Definir `RelevanceScorer.score(query_intent, title, abstract) -> 0..1` y un resultado con score, decisión, modelo y versión.
  - [ ] Definir políticas explícitas para abstract ausente, texto demasiado corto, idioma distinto y patentes con claims pero sin abstract.
  - [ ] Implementar un scorer léxico sencillo como fallback y referencia de pruebas.
  - [ ] Cerrar con commit sugerido `feat: add semantic intent and relevance scorer contract` y push a GitHub.

- [ ] **Tarea 5.3: Scorer local por embeddings**
  - [ ] Evaluar al menos dos modelos de embeddings multilingües sobre el dataset etiquetado antes de fijar dependencia y pesos.
  - [ ] Implementar carga diferida, procesamiento por lotes y similitud coseno entre intención y `title + abstract`.
  - [ ] Mantener inferencia local como opción predeterminada para el filtro; encapsular proveedores remotos detrás del mismo contrato si se añaden después.
  - [ ] Registrar nombre, revisión y licencia del modelo; fijar una versión reproducible y validar tamaño/tiempo de descarga.
  - [ ] Añadir pruebas deterministas con un scorer falso y pruebas de integración separadas para el modelo real.
  - [ ] Cerrar con commit sugerido `feat: add local embedding relevance scorer` y push a GitHub.

- [ ] **Tarea 5.4: Caché, auditoría y persistencia de decisiones**
  - [ ] Guardar embeddings por hash de texto + versión de modelo para no recalcular abstracts sin cambios.
  - [ ] Persistir score, umbral, decisión, motivo, modelo y fecha en una tabla de observaciones; no borrar resultados rechazados.
  - [ ] Invalidar el score cuando cambien intención, título, abstract, preprocesamiento o versión del modelo.
  - [ ] Implementar retención configurable para embeddings y una migración reversible de las nuevas tablas/columnas.
  - [ ] Añadir pruebas de cache hit/miss, invalidación, actualización de modelo y auditoría de descartes.
  - [ ] Cerrar con commit sugerido `feat: persist semantic relevance decisions` y push a GitHub.

- [ ] **Tarea 5.5: Filtro en pipeline, CLI y calibración**
  - [ ] Aplicar deduplicación antes del scoring y filtrar antes de generar el reporte principal; conservar una sección/archivo auditable de rechazados.
  - [ ] Añadir `--semantic-filter`, `--no-semantic-filter`, `--semantic-threshold 0..1` y variables equivalentes de configuración.
  - [ ] Permitir umbrales distintos para papers y patentes, con override por consulta vigilada.
  - [ ] Mostrar score y explicación breve en reportes, junto con conteos aceptados, rechazados y sin abstract.
  - [ ] Calibrar umbrales sobre el dataset etiquetado, comparar por fuente y documentar los casos límite.
  - [ ] Activar el filtro por defecto solo si alcanza el criterio de aceptación; mantener `--no-semantic-filter` como salida segura.
  - [ ] Cerrar con commit sugerido `feat: filter search results by semantic relevance` y push a GitHub.

---

## Fase 6: Integración, operación y release

**Objetivo:** Verificar los tres ámbitos y entregar una versión reproducible incluso cuando algunas APIs comerciales o condicionales no estén disponibles.

- [ ] **Tarea 6.1: Pruebas end-to-end y matriz de degradación**
  - [ ] Cubrir `papers`, `patents` y `all` con fuentes exitosas, vacías, truncadas, deshabilitadas, sin credenciales y temporalmente caídas.
  - [ ] Verificar checkpoints independientes por consulta/ámbito y que nunca avancen ante truncamiento o fallo de una fuente requerida.
  - [ ] Añadir tests de contrato grabados/sanitizados y tests live optativos marcados, nunca ejecutados por defecto en CI.
  - [ ] Medir tiempos, llamadas y memoria con y sin filtro semántico; establecer presupuestos documentados.
  - [ ] Cerrar con commit sugerido `test: cover unified search end to end` y push a GitHub.

- [ ] **Tarea 6.2: Documentación operativa y migración**
  - [ ] Documentar instalación, credenciales por proveedor, scopes, ejemplos, costes/restricciones, modelos semánticos y solución de errores.
  - [ ] Añadir una guía de migración desde `v0.4.0`, copia de seguridad de SQLite y verificación posterior.
  - [ ] Documentar qué fuentes funcionan sin credenciales y cómo se comporta el sistema si Lens, USPTO o WIPO no están disponibles.
  - [ ] Añadir ejemplos reproducibles de búsqueda solo papers, solo patentes y combinada, confirmando que el valor predeterminado es papers.
  - [ ] Cerrar con commit sugerido `docs: add unified search operations guide` y push a GitHub.

- [ ] **Tarea 6.3: Release integrada**
  - [ ] Ejecutar la matriz completa de CI en las versiones de Python soportadas y revisar seguridad/licencias de dependencias.
  - [ ] Confirmar que todos los adaptadores restringidos permanecen opt-in y que ninguna credencial está versionada.
  - [ ] Actualizar versión, historial de cambios y métricas del plan con el alcance realmente entregado; no marcar como completa una integración bloqueada por acceso externo.
  - [ ] Crear commit de release `release: prepare unified search release`.
  - [ ] Crear una etiqueta SemVer acorde al alcance terminado y subir rama + etiqueta a GitHub.

## Criterios globales de aceptación

- `paper-watcher search --query "..."` consulta únicamente papers por defecto.
- `--scope patents` no llama a APIs de papers y `--scope all` ejecuta ambos registros sin duplicar llamadas compartidas.
- Cada resultado conserva tipo documental, identidad canónica, fuentes y procedencia de campos.
- La ausencia de una credencial restringida degrada solo esa fuente y ofrece instrucciones accionables.
- Ningún checkpoint avanza si una fuente requerida falla o si la ventana queda truncada.
- El filtro semántico es auditable, reproducible, desactivable y mantiene al menos 90% de recall en el conjunto etiquetado.
- La suite no requiere red ni secretos; los tests live son optativos y están claramente marcados.
- Cada tarea principal queda respaldada por un commit atómico subido a GitHub.

---

## Historial de entregas anteriores

Las fases completadas se conservan como referencia; el nuevo trabajo comienza en la fase 2.

### Fase 0: Estabilización, Calidad y Correcciones Inmediatas (v0.3.1)

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

### Fase 1: Deduplicación Cross-Source, Nuevas Fuentes y Ventanas Temporales (v0.4.0)

**Objetivo:** Garantizar que la recopilación científica sea completa, sin duplicados entre preprints y revistas indexadas, y con capacidad de búsqueda incremental.

- [x] **Tarea 1.1: Deduplicación y fusión cross-source (Resolución por DOI / Título)**
  - [x] Analizar y rediseñar el esquema de base de datos para permitir que una misma publicación canónica vincule múltiples fuentes (ej. versión arXiv y posterior versión PubMed).
  - [x] Implementar algoritmo de fusión: si un paper entrante coincide en DOI o título normalizado con uno existente, asociar la nueva fuente/URL sin duplicar la entidad.
  - [x] Actualizar los reportes Markdown para indicar si un paper fue avistado tanto en preprint como en revista revisada por pares.

- [x] **Tarea 1.2: Integración de fuentes bioRxiv y medRxiv**
  - [x] Crear [`src/paper_watcher/sources/biorxiv.py`](file:///home/fernando/Escritorio/my_projects/scientific-paper-watcher/src/paper_watcher/sources/biorxiv.py) usando la API de bioRxiv/medRxiv.
  - [x] Mapear respuestas al modelo común `Paper`.
  - [x] Integrar bioRxiv y medRxiv al pipeline de búsqueda en `main.py` mediante consultas independientes y con aislamiento de fallos.
  - [x] Añadir tests para ambas fuentes y para la continuidad del pipeline si una de ellas falla.

- [x] **Tarea 1.3: Integración de OpenAlex / Europe PMC**
  - [x] Diseñar adaptador para OpenAlex (`sources/openalex.py`) para enriquecer papers con citas, tópicos y enlaces open-access a PDFs completos.
  - [x] Configurar llamadas opcionales controladas por flags o variables de entorno.

- [x] **Tarea 1.4: Búsquedas incrementales y ventanas de tiempo**
  - [x] Agregar columna `last_checked_at` en la tabla `watch_queries`.
  - [x] Añadir flag de CLI: `--since` / `--days N` en el comando `paper-watcher run`.
  - [x] Modificar adaptadores de fuentes para filtrar por rango de fechas (ej. `mindate`/`maxdate` en PubMed, `submittedDate` en arXiv) y traer solo novedades efectivas.

---
