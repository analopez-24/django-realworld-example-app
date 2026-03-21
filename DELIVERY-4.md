# Delivery 4: Estrategia de Arquitectura & Developer Experience

| Campo       | Descripción                                                   |
|-------------|---------------------------------------------------------------|
| **Proyecto**| Conduit RealWorld API                                         |
| **Grupo 8** | Ana López y Javier Martinez                                  |
| **Entrega** | Delivery 4 – Architecture Strategy & DevEx                   |

---

## Entregables

| # | Entregable | Archivo | Criterio del Rubric |
|---|------------|---------|---------------------|
| 1 | Configuración Docker completa | `docker-compose.yml` | El entorno levanta con un solo comando en menos de 5 minutos |
| 2 | Documento de decisión arquitectónica | `ADR-DOCUMENT.md` | ADR sigue el formato RFC con argumentos respaldados por datos |

---

## Configuración en un solo comando

Clonar el repositorio y ejecutar:

```bash
docker compose up --build
```

No se requieren pasos manuales. El entorno completo, base de datos, migraciones y servidor, levanta automáticamente.

**Lo que ocurre al ejecutar el comando:**

1. Docker descarga las imágenes base de Python 3.10 y PostgreSQL 15
2. Se instalan todas las dependencias del proyecto
3. PostgreSQL inicia y espera hasta estar saludable
4. Django corre todas las migraciones automáticamente
5. El servidor queda funcionando en `http://localhost:8000`

**Verificación:** Abrir el navegador en `http://localhost:8000/api/articles`, se debería de ver algo como:

```json
{"articles": [], "articlesCount": 0}
```

---

## Arquitectura del Stack (Delivery 4)

```
┌─────────────────────────────────────────────┐
│           Red Docker: conduit_network        │
│                                             │
│  ┌──────────────────┐   ┌────────────────┐  │
│  │   Django App     │──▶│  PostgreSQL 15  │  │
│  │   :8000          │   │  :5432          │  │
│  └──────────────────┘   └────────────────┘  │
└─────────────────────────────────────────────┘
```

| Servicio | Imagen | Rol |
|----------|--------|-----|
| `app` | `python:3.10-slim` | API de Django (modernizada desde Python 3.5) |
| `db` | `postgres:15-alpine` | Base de datos principal (reemplaza SQLite3 — ver ADR-001) |

---

## Resumen del ADR-001

**Decisión**: Migrar la base de datos principal de SQLite3 a PostgreSQL 15.

**¿Por qué es necesario?**

| Problema con SQLite3 | Impacto Medido |
|----------------------|----------------|
| Solo 1 escritor concurrente permitido | Bloquea todos los workers de Django en paralelo |
| Sin connection pooling | Procesamiento serial de requests |
| File-level locking | Causa `OperationalError: database is locked` |
| Sin recuperación ante crashes | Pérdida de datos al cerrar el contenedor inesperadamente |
| Techo de rendimiento de escritura | ~1 req/s vs ~10,000 req/s de PostgreSQL |

El documento completo incluye contexto, decisión, cuatro alternativas analizadas, consecuencias positivas y negativas, plan de implementación por fases y métricas de éxito medibles.

---

## Cambios Realizados al Proyecto Original

Para que el entorno funcione correctamente fue necesario modernizar el proyecto legacy:

| Archivo | Cambio | Razón |
|---------|--------|-------|
| `requirements.txt` | Se pasó de Django 1.10 a 3.2, dependencias actualizadas | Django 1.10 es incompatible con Python 3.10 |
| `conduit/settings.py` | Base de datos configurada via `DATABASE_URL`, CORS actualizado | Compatibilidad con Docker y versiones modernas |
| `conduit/urls.py` | Eliminados `namespace` sin `app_name` | Requerimiento de Django 3.2 |
| `docker-compose.yml` | Nuevo, define el stack completo | Entregable principal del Delivery 4 |
| `Dockerfile` | Nuevo, construye la imagen de la app | Requerido por el compose |
| `.env.example` | Nuevo, plantilla de variables de entorno | Buena práctica, no se sube el `.env` real |

---

## Comandos Útiles

```bash
# Levantar el entorno
docker compose up --build

# Ver logs de la aplicación
docker compose logs -f app

# Detener todos los servicios
docker compose down

# Detener y borrar la base de datos (inicio limpio)
docker compose down -v
```

---

## Conexión con Entregas Anteriores

Este delivery se apoya directamente en el trabajo previo:

- **Delivery 1** — El `ONBOARDING_LOG.md` documentó la fricción causada por SQLite al intentar correr el proyecto en entornos modernos. El `docker-compose.yml` resuelve exactamente ese problema.
- **Delivery 2** — El `TECH_DEBT_AUDIT.md` clasificó la base de datos SQLite como ítem **P1 (Crítico)**. El ADR-001 propone formalmente la solución a ese ítem.

---

## Estructura del Repositorio (Delivery 4)

```
django-realworld-example-app/
├── manage.py
├── requirements.txt                    modificado: dependencias modernizadas
├── conduit/
│   ├── settings.py                     modificado: DATABASE_URL + CORS fix
│   ├── urls.py                         modificado: compatibilidad Django 3.2
│   └── apps/
│       ├── articles/
│       ├── authentication/
│       ├── profiles/
│       └── core/
├── docker-compose.yml                  NUEVO — entregable principal
├── Dockerfile                          NUEVO — build de la imagen
├── .env.example                        NUEVO — plantilla de variables
└── ADR-001-postgresql-migration.md     NUEVO — RFC estratégico
```
