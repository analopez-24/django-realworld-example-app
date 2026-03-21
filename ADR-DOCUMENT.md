# ADR: Migración de SQLite3 a PostgreSQL como Motor de Base de Datos Principal

| Campo        | Descripción                                                  |
|-------------|---------------------------------------------------------------|
| **Título**   | Migrar la base de datos principal de SQLite3 a PostgreSQL 15 |
| **Estado**   | Propuesto                                                    |
| **Grupo 8**  | Ana López y Javier Martinez                                  |
| **Entrega**  | Delivery 4 – Architecture Strategy & DevEx                   |

---

## 1. Contexto

### 1.1 Estado Actual

La aplicación Conduit RealWorld fue construida usando SQLite3 como único motor de base de datos (configurado en `conduit/settings.py`). Esta fue una decisión aceptable para un prototipo o aplicación de demostración, pero representa riesgos críticos ahora que el sistema está siendo estabilizado y modernizado.

Nuestro **análisis de reverse engineering del Delivery 1** identificó cinco bounded contexts: Authentication, Content Management, Social Profile, Engagement y Feed Aggregation. Todos comparten un único archivo SQLite (`db.sqlite3` en la raíz del proyecto), lo cual crea un único punto de falla y un techo de escalabilidad a nivel de datos.

Nuestro **Tech Debt Audit del Delivery 2** calificó la configuración de base de datos como un riesgo P1 (Crítico), citando específicamente:

- Sin connection pooling -> procesamiento serial de requests bajo carga
- Sin soporte de escrituras concurrentes -> el file-level locking de SQLite bloquea workers paralelos de Django
- Sin WAL-mode configurado -> riesgo de corrupción de datos ante un cierre inesperado
- `SECRET_KEY` hardcodeado en `settings.py` junto a la ruta de la base de datos → exposición de seguridad

### 1.2 Datos Observados

| Métrica | Valor | Fuente |
|---------|-------|--------|
| Bounded contexts compartiendo un mismo archivo de base de datos | 5 | Context Map — Delivery 1 |
| Workers de Django bloqueados por el write lock de SQLite | 100% | Documentación oficial de SQLite |
| Rendimiento de escrituras concurrentes (SQLite) | ~1 req/s | Límites oficiales de SQLite |
| Rendimiento de escrituras concurrentes (PostgreSQL 15) | ~10,000 req/s | Benchmarks de pgbench |
| Ítems de deuda técnica P1 relacionados a la base de datos | 3 | `TECH_DEBT_AUDIT.md` — Delivery 2 |
| Incidentes de producción causados por bloqueos de SQLite | Documentados | gothinkster/realworld#533 |

### 1.3 Planteamiento del Problema

> **SQLite no es una base de datos de nivel productivo.** Su filosofía de diseño, sin configuración, archivo único, sin servidor, es incompatible con un despliegue de Django con múltiples workers, entornos distribuidos, o cualquier flujo de trabajo en equipo donde los desarrolladores necesiten compartir estado entre contenedores o máquinas.

Esto genera los siguientes riesgos concretos:

1. **Riesgo operacional**: Un crash de un proceso Django puede corromper el archivo SQLite sin ninguna ruta de recuperación automática.
2. **Degradación del Developer Experience**: Dos desarrolladores no pueden correr pruebas de integración simultáneamente sin conflictos de file lock.
3. **Incompatibilidad con la nube**: Los despliegues basados en contenedores (Docker, Kubernetes) pierden el estado de la base de datos en cada reinicio del contenedor a menos que se configure un montaje de volúmenes complejo.
4. **Cero observabilidad**: SQLite no tiene métricas de conexión, ni slow query log, ni equivalente a `pg_stat_statements`.
5. **Techo de migración**: Una futura migración a microservicios requiere que cada servicio tenga su propia base de datos.

---

## 2. Decisión

**Migraremos el motor de base de datos principal de SQLite3 a PostgreSQL 15.**

Esta migración se implementará usando el patrón **Expand–Contract** (también conocido como parallel-run migration) para evitar tiempo fuera de servicio y reducir el riesgo:

1. **Expand:** Correr PostgreSQL junto a SQLite en el entorno Docker (ambos activos).
2. **Migrate:** Usar `pgloader` o `django-dbbackup` para transferir los datos.
3. **Contract:** Eliminar la configuración de SQLite una vez que PostgreSQL esté validado como primario.

La migración apunta específicamente a PostgreSQL 15 por sus mejoras en replicación lógica, soporte del comando `MERGE` y rendimiento en cargas de trabajo con JSON (relevante para la capa de salida de `ConduitJSONRenderer`).

### 2.1 Estado Objetivo de la Arquitectura

```
Antes (legacy)                        Después (Delivery 4+)
──────────────                        ─────────────────────
┌──────────────────┐                  ┌───────────────────────┐
│  Django (1 proc) │                  │  Django (N procesos)  │
│                  │                  │  gunicorn workers     │
│  settings.py     │                  └──────────┬────────────┘
│  DATABASE = {    │                             │ connection pool
│   ENGINE:sqlite3 │                             ▼
│   NAME: db.sqlite│                  ┌───────────────────────┐
│  }               │                  │    PostgreSQL 15       │
└────────┬─────────┘                  │  (servicio dedicado)  │
         │                            │  - WAL habilitado     │
         ▼                            │  - backups PITR       │
    [db.sqlite3]                      │  - pg_stat_statements │
    (archivo único)                   └───────────────────────┘
```

---

## 3. Alternativas Consideradas

### 3.1 No hacer nada (mantener SQLite3)

| Criterio | Evaluación |
|----------|------------|
| Costo de implementación | $0 |
| Riesgo | Crítico pues bloquea todo escalamiento futuro |
| Impacto en Developer Experience | Negativo pues no se puede containerizar correctamente |
| Preparación para la nube | Incompatible con patrones de ECS/GKE/AKS |

Se descartó porque perpetúa la deuda técnica central identificada en el Delivery 2. Cualquier prueba de rendimiento o carga durante entregas futuras sería inválida.

### 3.2 MySQL 8

PostgreSQL y MySQL son ambas opciones viables. Elegimos PostgreSQL sobre MySQL por estas razones:

- El ORM de Django tiene soporte de primera clase para PostgreSQL (`JSONField`, `ArrayField`, UUID nativo, búsqueda de texto completo) versus los equivalentes limitados de MySQL.
- El módulo `conduit/apps/articles` usa renderizado JSON extensivamente, el tipo `JSONB` de PostgreSQL ofrece JSON indexable, algo que el tipo `JSON` de MySQL no soporta con rendimiento equivalente.
- PostgreSQL es la recomendación por defecto en la documentación oficial de Django para despliegues productivos.
- Licencia open-source (PostgreSQL License) versus la doble licencia de MySQL (GPL + Oracle Commercial).

Se descartó porque PostgreSQL ofrece mejor integración con Django y mayor alineación con el stack técnico del proyecto.

### 3.3 PlanetScale (MySQL serverless)

Atractivo por su modelo de branching, pero introduce dependencia de vendor y requiere cambios de esquema para foreign keys (PlanetScale no soporta restricciones FK por defecto). El modelo de Conduit depende fuertemente de FKs (`Article→Profile`, `Comment→Article`, `Follow→Profile`), lo que requeriría refactoring significativo del ORM fuera del alcance actual.

Se rechazó porque la relación costo-beneficio es desfavorable dado el modelo de datos relacional del proyecto.

### 3.4 MongoDB (almacén de documentos)

El spec de RealWorld es inherentemente relacional. Las relaciones Article–Comment–Tag, el grafo de Follow y los contadores de Favorites son todos de naturaleza relacional. Migrar a MongoDB requeriría reescribir los 12 serializers, eliminar el ORM de Django por completo y perder Django Admin y todas las herramientas relacionadas.

Se rechazó porque el modelo de datos no se beneficia del almacenamiento de documentos y el costo de migración es prohibitivo.

---

## 4. Consecuencias

### 4.1 Consecuencias Positivas

| Beneficio | Evidencia / Datos |
|-----------|-------------------|
| **Escrituras concurrentes** | PostgreSQL soporta MVCC — múltiples escritores sin bloqueos. SQLite permite solo 1 escritor a la vez. |
| **Integridad de datos** | Cumplimiento ACID completo con WAL + `synchronous_commit`. SQLite en modo por defecto no es crash-safe. |
| **Observabilidad** | `pg_stat_statements`, `pg_stat_activity`, Prometheus `postgres_exporter` — sin equivalentes en SQLite. |
| **Escalamiento horizontal** | Read replicas vía streaming replication. Sin equivalente en SQLite. |
| **Preparación para la nube** | Soporte de primera clase en AWS RDS, GCP Cloud SQL, Azure Database for PostgreSQL. |
| **Developer Experience** | Cada desarrolladora corre un contenedor de base de datos aislado. Sin conflictos de archivos compartidos. `docker compose up` da a todas un estado limpio. |
| **Habilitación del Strangler Fig** | Cada futuro microservicio puede tener su propio esquema o cluster de PostgreSQL — requisito fundamental para el plan de modularización futuro. |

### 4.2 Consecuencias Negativas y Mitigaciones

| Riesgo | Severidad | Mitigación |
|--------|-----------|------------|
| Esfuerzo de migración | Media | 2 días-desarrollador estimados. `pgloader` automatiza el 80% de la migración SQLite→PG. |
| Mayor complejidad de infraestructura | Baja | Gestionada vía Docker Compose (local) y servicios de base de datos administrados en la nube. |
| Ligeramente mayor uso de recursos locales | Baja | La imagen `postgres:15-alpine` agrega ~80MB de RAM. Aceptable dado el mínimo de 4GB de Docker. |
| Curva de aprendizaje del equipo | Baja | Ambas ingenieras tienen experiencia previa con PostgreSQL. El ORM de Django abstrae la mayoría de las diferencias. |
| Gestión de conexiones | Media | Se debe configurar `pgBouncer` para producción. No requerido para el alcance del Delivery 4. |

### 4.3 Fuera del Alcance (ADRs Futuros)

- Connection pooling con PgBouncer 
- Configuración de read replica para el contexto de Feed Aggregation 
- Estrategia de backups Point-in-Time Recovery

---

## 5. Plan de Implementación

### Fase 0 — Validación

```bash
# Verificar que Django puede conectarse al contenedor de PostgreSQL
docker compose up db -d
python manage.py check --database default
```

### Fase 1 — Migración de Esquema

```bash
# Instalar dependencias
pip install psycopg2-binary dj-database-url

# Correr migraciones contra PostgreSQL
python manage.py migrate --database default
```

**Cambio en `settings.py`:**
```python
# ANTES
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.path.join(BASE_DIR, 'db.sqlite3'),
    }
}

# DESPUÉS
import dj_database_url
DATABASES = {
    'default': dj_database_url.config(
        default='sqlite:///db.sqlite3'
    )
}
```

### Fase 2 — Transferencia de Datos

```bash
# Si hay datos existentes en SQLite que preservar:
python manage.py dumpdata --natural-foreign --natural-primary \
    -e contenttypes -e auth.Permission \
    --indent 2 > fixtures/sqlite_export.json

python manage.py loaddata fixtures/sqlite_export.json
```

### Fase 3 — Pruebas y Limpieza 

```bash
# Correr suite de pruebas contra PostgreSQL
python manage.py test

# Eliminar archivo SQLite y referencias
git rm db.sqlite3
echo "db.sqlite3" >> .gitignore
```

---

## 6. Métricas de Éxito

| Métrica | Objetivo | Método de Medición |
|---------|----------|--------------------|
| Todas las pruebas del CI pasan contra PostgreSQL | 100% | GitHub Actions  |
| `docker compose up` completa en menos de 5 minutos | < 300s | `time docker compose up --build` |
| Cero pérdida de datos durante la migración | 0 registros perdidos | Comparación de conteo de filas antes y después |
| Pruebas de humo de la API pasan post-migración | Todos los endpoints responden | `curl http://localhost:8000/api/articles` |
| Sin referencias a SQLite en settings | 0 referencias | `grep -r sqlite3 conduit/settings.py` |

---

## 7. Referencias

- [Cuándo usar SQLite — documentación oficial de SQLite](https://www.sqlite.org/whentouse.html): Recomienda explícitamente no usarlo para sitios con escrituras concurrentes.
- [Documentación de Django — notas de PostgreSQL](https://docs.djangoproject.com/en/4.2/ref/databases/#postgresql-notes)
- [Patrón Expand-Contract — Martin Fowler, Refactoring Databases](https://martinfowler.com/articles/evodb.html)
- [gothinkster/realworld Issue #533](https://github.com/gothinkster/realworld/issues/533): Fallas de concurrencia reportadas en SQLite en implementaciones de RealWorld.
- [Notas de la versión PostgreSQL 15](https://www.postgresql.org/docs/15/release-15.html): Comando MERGE, replicación lógica mejorada.
- Delivery 1 — [`ONBOARDING_LOG.md`](https://github.com/analopez-24/django-delivery-1/blob/main/ONBOARDING_LOG.md)
- Delivery 2 — [`TECH_DEBT_AUDIT.md`](https://github.com/analopez-24/django-delivery-1/blob/main/TECH_DEBT_AUDIT.md)

---

