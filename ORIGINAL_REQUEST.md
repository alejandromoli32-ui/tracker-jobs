# Original User Request

## Initial Request — 2026-09-21T22:17:45Z

# Multi-Profile Job Tracker & Hunter Engine (Colombia & Remote)

Sistema automatizado y modular en Python para la búsqueda, extracción, filtrado inteligente y seguimiento de vacantes laborales remotas/virtuales en Colombia, diseñado con arquitectura multi-perfil (hasta 4 perfiles configurables) e implementado inicialmente para una Ingeniera Civil Senior con especialidad en Vías y Seguridad y Salud en el Trabajo (SST).

Working directory: c:/Users/Admin/Downloads/TRACKER_JOBS
Integrity mode: development

## Requirements

### R1. Multi-Profile Configuration & Architecture
Crear un sistema extensible donde cada perfil laboral se defina mediante un archivo de configuración declarativo (YAML/JSON). El sistema debe soportar al menos 4 perfiles independientes con sus propias palabras clave, títulos de cargo, filtros excluyentes, años mínimos de experiencia y parámetros de búsqueda.
- Perfil 1 (Inicial): Ingeniera Civil (15+ años de experiencia total), Especialista en Vías / Infraestructura Vial (5+ años de experiencia) y Especialista en Seguridad y Salud en el Trabajo / SST (5+ años de experiencia, con licencia SST). Modalidad estrictamente virtual / remota / teletrabajo aplicable en Colombia.

### R2. Job Scraping & Aggregation Engine
Motor de búsqueda y extracción periódica de ofertas laborales que consulte bolsas de empleo y plataformas relevantes en Colombia y modalidades remotas (ej. LinkedIn Jobs, Computrabajo, ElEmpleo, Indeed, o Google Jobs API/Scraping). Debe contar con manejo de paginación, control de reintentos, evasión de bloqueos básicos y normalización de los datos extraídos (título, empresa, enlace directo, descripción completa, fecha de publicación, ubicación/modalidad, rango salarial si está disponible).

### R3. Intelligent Matching & Filtering Scoring
Módulo de evaluación y puntuación que procese cada vacante extraída contra el perfil activo:
- Verificación estricta de modalidad remota/virtual o teletrabajo.
- Puntuación de afinidad técnica (0 a 100) evaluando experiencia requerida, especialidades (Vías y/o SST), palabras clave afines y detección de requisitos excluyentes.
- Generación de un resumen explicativo corto para cada vacante que indique por qué coincide con el perfil y posibles observaciones (ej. "Requiere tarjeta profesional COPNIA y licencia SST").

### R4. Automated Output & Tracker Storage
Persistencia y exportación estructurada en formato Excel (`.xlsx`) y CSV de las ofertas encontradas que superen el umbral de coincidencia:
- Registro de deduplicación (evitar guardar ofertas repetidas en ejecuciones sucesivas).
- Columnas organizadas: ID/Hash, Fecha Detección, Título, Empresa, Score %, Modalidad, Enlace Directo, Salario, Resumen de Afinidad, Estado (ej. 'Nueva', 'Por revisar', 'Postulado', 'Descartado').
- Capacidad de ejecutar actualizaciones incrementales sin sobrescribir el estado de las postulaciones previas.

## Verification Resources
- Set de vacantes de prueba (descripciones sintéticas y reales representativas: 3 vacantes ideales de vías/SST remotas, 3 vacantes presenciales que deben descartarse, 3 vacantes de ingeniería civil no afines).

## Acceptance Criteria

### Extracción y Ejecución
- [ ] El motor de extracción recupera vacantes funcionales con URLs válidas y fecha reciente desde al menos 2 fuentes públicas reconocidas en Colombia/remoto.
- [ ] El sistema maneja errores de red y cambios de estructura de página de forma resiliente sin terminar abruptamente.

### Clasificación y Filtros
- [ ] Las vacantes 100% presenciales en obra o fuera de la modalidad virtual son filtradas o marcadas con penalización explícita.
- [ ] Las vacantes con afinidad superior a 70 puntos corresponden fehacientemente a perfiles de ingeniería civil, interventoría, gerencia de proyectos viales, consultoría de transporte o gestión de SST.

### Modularidad Multi-Perfil
- [ ] Añadir un segundo, tercer o cuarto perfil no requiere modificar el código fuente principal, únicamente agregar un nuevo archivo de configuración.

### Pruebas y Reporte
- [ ] La suite de pruebas automatizadas (`pytest`) valida la extracción, la deduplicación, el filtrado por score y la persistencia en Excel/CSV.
- [ ] El archivo de Excel generado contiene formato legible, enlaces clicables y persistencia del estado de seguimiento.
