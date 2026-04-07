# Conduit API — Django RealWorld Example App

[![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Django](https://img.shields.io/badge/Django-4.x-092E20?logo=django&logoColor=white)](https://www.djangoproject.com/)
[![DRF](https://img.shields.io/badge/Django%20REST%20Framework-3.x-red)](https://www.django-rest-framework.org/)
[![Docker](https://img.shields.io/badge/Docker-Contenedorizado-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)
[![Licencia: MIT](https://img.shields.io/badge/Licencia-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![CI/CD](https://img.shields.io/badge/CI%2FCD-GitHub%20Actions-2088FF?logo=github-actions&logoColor=white)](https://github.com/features/actions)
[![Seguridad](https://img.shields.io/badge/Seguridad-Reforzada-green?logo=shield)](./docs/SECURITY.md)
[![FinOps](https://img.shields.io/badge/FinOps-Optimizado-blueviolet)](./DELIVERY-5.md)

> API REST de nivel productivo que implementa la especificación [RealWorld](https://github.com/gothinkster/realworld) — modernizada, asegurada y optimizada por un equipo de ingeniería como parte de un proyecto de recuperación de aplicación legacy.

---

## 📋 Tabla de Contenidos

- [Descripción General](#descripción-general)
- [Arquitectura](#arquitectura)
- [Inicio Rápido](#inicio-rápido)
- [Referencia de la API](#referencia-de-la-api)
- [Optimizaciones de Rendimiento](#optimizaciones-de-rendimiento)
- [Seguridad](#seguridad)
- [Entregables del Proyecto](#entregables-del-proyecto)
- [Desarrollo](#desarrollo)
- [Contribuciones](#contribuciones)

---

## Descripción General

**Conduit** es una API de plataforma de blogs sociales. Los usuarios pueden:
- Registrarse y autenticarse con JWT
- Publicar, editar y eliminar artículos
- Comentar en artículos
- Seguir a otros usuarios
- Marcar artículos como favoritos
- Explorar artículos por tag o autor

Este fork fue tomado como una aplicación legacy en estado crítico y modernizado a lo largo de 5 entregables, desde la ingeniería inversa y el refuerzo de seguridad, hasta la optimización FinOps y esta entrega final.

---

## Arquitectura

```
┌─────────────────────────────────────────────────────────┐
│              Cliente (Navegador / Aplicación)            │
└───────────────────────────┬─────────────────────────────┘
                            │ HTTPS / JWT Auth
┌───────────────────────────▼─────────────────────────────┐
│               Django REST Framework (DRF)               │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌─────────┐ │
│  │ /articles│  │  /users  │  │/profiles │  │  /tags  │ │
│  └──────────┘  └──────────┘  └──────────┘  └─────────┘ │
│                       Django ORM                        │
│            (select_related + prefetch_related)          │
└───────────────────────────┬─────────────────────────────┘
                            │
          ┌─────────────────┼──────────────────┐
          │                 │                  │
┌─────────▼──────┐  ┌───────▼──────┐  ┌───────▼──────┐
│  PostgreSQL DB │  │  Redis Caché │  │ Almacenamiento│
│  (Datos princi)│  │  (Tags, etc) │  │  (Estáticos)  │
└────────────────┘  └──────────────┘  └──────────────┘
```

### Estructura de Módulos

```
conduit/
├── apps/
│   ├── articles/           # Artículos, Tags, Comentarios, Favoritos
│   │   ├── models.py
│   │   ├── views.py        # Optimizado para FinOps 
│   │   ├── serializers.py
│   │   └── urls.py
│   ├── authentication/     # JWT Auth, registro/login de usuarios
│   └── profiles/           # Perfiles de usuario, sistema de seguimiento
├── settings.py
└── urls.py
```

---

## Inicio Rápido

### Requisitos Previos

- Docker & Docker Compose
- Python 3.11+ (para desarrollo local)

### 1. Clonar y configurar

```bash
git clone https://github.com/analopez-24/django-realworld-example-app.git
cd django-realworld-example-app

cp .env.example .env
# Editar .env con la configuración local
```

### 2. Ejecutar con Docker 

```bash
docker-compose up --build
```

La API estará disponible en `http://localhost:8000`.

### 3. Ejecutar localmente

```bash
python -m venv venv
source venv/bin/activate       # Windows: venv\Scripts\activate

pip install -r requirements.txt

python manage.py migrate
python manage.py createsuperuser  # opcional

python manage.py runserver
```

---

## Referencia de la API

URL Base: `http://localhost:8000/api`

| Método | Endpoint | Descripción |
|---|---|---|
| `POST` | `/users` | Registrar usuario |
| `POST` | `/users/login` | Iniciar sesión → JWT |
| `GET` | `/user` | Obtener usuario actual |
| `PUT` | `/user` | Actualizar usuario |
| `GET` | `/articles` | Listar artículos |
| `POST` | `/articles` | Crear artículo |
| `GET` | `/articles/feed` | Feed personal |
| `GET` | `/articles/:slug` | Obtener artículo |
| `PUT` | `/articles/:slug` | Actualizar artículo |
| `DELETE` | `/articles/:slug` | Eliminar artículo |
| `POST` | `/articles/:slug/favorite` | Marcar favorito |
| `GET` | `/articles/:slug/comments` | Listar comentarios |
| `POST` | `/articles/:slug/comments` | Agregar comentario |
| `GET` | `/profiles/:username` | Obtener perfil | 
| `POST` | `/profiles/:username/follow` | Seguir usuario |
| `GET` | `/tags` | Listar todos los tags |

Especificación completa: [RealWorld API Spec](https://realworld-docs.netlify.app/docs/specs/backend-specs/endpoints)

---

## Optimizaciones de Rendimiento

> **Entrega 5 — Optimización FinOps**

### Problema: N+1 Query Problem

El endpoint original `GET /api/articles` disparaba 151 queries a la base de datos por request para 50 artículos, una para la lista de artículos, más 3 por cada artículo (autor, tags, favoritos).

### Solución Aplicada

```python
# conduit/apps/articles/views.py
Article.objects.select_related(
    'author',
    'author__profile',      # SQL JOIN: 1 query en lugar de N
).prefetch_related(
    'tags',                 # Batch: 1 query para todos los tags
    'favorited_by',         # Batch: 1 query para todos los favoritos
)
```

### Resultados

| Artículos | Queries Antes | Queries Después | Mejora de Velocidad |
|:---:|:---:|:---:|:---:|
| 10 | 31 | 3 | **82% más rápido** |
| 25 | 76 | 3 | **93% más rápido** |
| 50 | 151 | 3 | **96% más rápido** |
| 100 | 301 | 3 | **98% más rápido** |

Adicionalmente: `/api/tags` ahora usa caché de Redis por 5 minutos, reduciendo ese endpoint de N consultas/minuto a 1.

Reporte completo del benchmark: [DELIVERY-5.md](./DELIVERY-5.md)

---

## Seguridad

La aplicación fue reforzada a lo largo de múltiples entregables:

- Secrets movidos a `.env` (sin credenciales en el código)
- `DEBUG=False` en la configuración de producción
- `ALLOWED_HOSTS` restringido
- Tokens JWT para autenticación (sin cookies de sesión)
- Vulnerabilidades de dependencias auditadas con `pip-audit`
- La imagen Docker usa usuario sin privilegios de root

Reporte completo de registros de decisiones arquitectónicas: [ADR-DOCUMENT.md](./ADR-DOCUMENT.md)

---

## Entregables del Proyecto

| # | Entregable | Descripción | Enlace |
|---|---|---|---|
| E1 | Discovery & Reverse Engineering | Auditoría del código, grafo de dependencias, matriz de riesgos | [Repo](https://github.com/analopez-24/django-delivery-1) |
| E2 | Governance & Technical Debt Audit | Configuración de un CI workflow que mide la complejidad ciclomática y la cobertura del código |[Repo](https://github.com/analopez-24/django-delivery-1) |
| E3 | Security Hardening | Seguridad de la cadena de suministro | [Repo](https://github.com/analopez-24/django-delivery-1) |
| E4 | Architecture Strategy & DevEx | ADRs, Docker, pipeline CI/CD | [DELIVERY-4.md](./DELIVERY-4.md) |
| E5 | FinOps Optimization & Final Defense | Corrección N+1, benchmarks, análisis de costos en la nube | [DELIVERY-5.md](./DELIVERY-5.md) |

---

## Desarrollo

### Ejecutar pruebas

```bash
python manage.py test
```

### Ejecutar benchmark

```bash
python benchmarks/benchmark_articles.py
```

### Linting

```bash
pip install flake8
flake8 conduit/
```

### Variables de Entorno

| Variable | Descripción | Valor por Defecto |
|---|---|---|
| `SECRET_KEY` | Clave secreta de Django | Requerida |
| `DEBUG` | Modo de depuración | `False` |
| `DATABASE_URL` | Cadena de conexión a PostgreSQL | SQLite (desarrollo) |
| `REDIS_URL` | Redis para caché | `redis://localhost:6379` |
| `ALLOWED_HOSTS` | Lista de hosts separados por coma | `localhost` |

---

*Originalmente forkeado de [gothinkster/django-realworld-example-app](https://github.com/gothinkster/django-realworld-example-app)*
