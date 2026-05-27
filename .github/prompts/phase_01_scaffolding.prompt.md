---
mode: agent
description: >
  Fase 1 — Scaffolding de Event Edge: crea la estructura base del proyecto,
  pyproject.toml, entrypoint, config y app FastAPI. Sin lógica de negocio.
tools:
  - read_file
  - create_file
  - run_in_terminal
  - file_search
---

# Fase 1 — Scaffolding

## Prerrequisitos

Leer antes de comenzar:
- `Backtest_Forge/pyproject.toml` → patrón de dependencias y estructura de proyecto
- `market_data_hub/api/app.py` → patrón de factory `create_app()`
- `Event_Edge/.github/instructions/global.instructions.md` → convenciones del proyecto

## Objetivo

Crear la estructura de directorios y archivos base de `Event_Edge/`. Al finalizar esta fase:
- El backend arranca con `uvicorn backend.main:app --port 8100`
- `GET /` responde `{"service": "Event Edge", "version": "0.1.0"}`
- `GET /docs` expone la UI de Swagger
- Los imports entre módulos funcionan sin errores

## Archivos a crear

### `Event_Edge/pyproject.toml`
```toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.backends.legacy:build"

[project]
name = "event-edge"
version = "0.1.0"
description = "Herramienta de estudio probabilístico de eventos Earnings & Gap para acciones americanas"
requires-python = ">=3.11"
dependencies = [
    "pandas>=2.0",
    "numpy>=1.26",
    "scipy>=1.12",
    "pydantic>=2.0",
    "pydantic-settings>=2.0",
    "fastapi>=0.110",
    "uvicorn[standard]>=0.29",
    "httpx>=0.27",
    "yfinance>=0.2.38",
    "pandas-ta>=0.3.14",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "httpx>=0.27",
    "ruff>=0.4",
]

[tool.setuptools.packages.find]
where = ["."]
include = ["backend*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
markers = [
    "unit: tests sin conexión real",
    "integration: tests que requieren servicios externos",
    "smoke: prueba rápida de smoke",
]
```

### `Event_Edge/README.md`
Descripción breve del proyecto, instrucciones de instalación y arranque.

### `Event_Edge/start_server.ps1`
Script PowerShell que:
1. Activa el entorno conda `event_edge` (si existe) o usa el entorno activo
2. Arranca `uvicorn backend.main:app --reload --port 8100`

### `Event_Edge/backend/__init__.py`
Vacío.

### `Event_Edge/backend/config.py`
```python
from __future__ import annotations
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # MDH
    mdh_base_url: str = "http://localhost:8000/api/v1"
    mdh_api_key: str = ""
    mdh_enabled: bool = True          # False → yfinance fallback

    # MT5
    mt5_login: int = 0
    mt5_password: str = ""
    mt5_server: str = ""

    # TWS
    tws_api_key: str = ""             # vacío → 403 en endpoints TWS

    # App
    debug: bool = False
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    model_config = SettingsConfigDict(env_prefix="EE_", env_file=".env", extra="ignore")

_settings: Settings | None = None

def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
```

### `Event_Edge/backend/api/__init__.py`
Vacío.

### `Event_Edge/backend/api/app.py`
Factory `create_app()` que:
- Crea `FastAPI` con título, descripción y versión
- Agrega `CORSMiddleware` con `cors_origins` de settings
- Incluye los 4 routers (control, assets, events, analysis) — importarlos aunque los módulos sean stubs vacíos
- Define `GET /` → `{"service": "Event Edge", "version": "0.1.0", "docs": "/docs"}`

### `Event_Edge/backend/api/routers/__init__.py`
Vacío.

### `Event_Edge/backend/api/routers/control.py`
Solo el router declarado con `prefix="/api/v1/control"`. Sin endpoints todavía — dejarlos como `TODO`.

### `Event_Edge/backend/api/routers/assets.py`
Solo el router declarado con `prefix="/api/v1/assets"`. Sin endpoints todavía.

### `Event_Edge/backend/api/routers/events.py`
Solo el router declarado con `prefix="/api/v1/events"`. Sin endpoints todavía.

### `Event_Edge/backend/api/routers/analysis.py`
Solo el router declarado con `prefix="/api/v1/analysis"`. Sin endpoints todavía.

### `Event_Edge/backend/main.py`
```python
from backend.api.app import app

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8100, reload=True)
```

### `Event_Edge/backend/core/__init__.py`
Vacío.

### `Event_Edge/backend/data/__init__.py`
Vacío.

### `Event_Edge/tests/__init__.py`
Vacío.

### `Event_Edge/tests/unit/__init__.py`
Vacío.

### `Event_Edge/tests/integration/__init__.py`
Vacío.

## Criterios de aceptación

```bash
# Desde Event_Edge/
cd c:\Users\Junior\Proyectos\EdgeStocks_sistem\Event_Edge

# 1. El servidor arranca sin errores de import
uvicorn backend.main:app --port 8100

# 2. Health check root
curl -s http://localhost:8100/
# → {"service":"Event Edge","version":"0.1.0","docs":"/docs"}

# 3. Swagger accesible
curl -s http://localhost:8100/docs -o /dev/null -w "%{http_code}"
# → 200

# 4. Sin errores de Pylance/mypy en backend/config.py y backend/api/app.py
```

## Restricciones

- NO implementar lógica de negocio en esta fase
- `cors_origins` nunca hardcodeado como `["*"]`; siempre desde settings
- La variable `_settings` se resetea con `_settings = None` en fixtures de test (ya documentado en config.py)
- `mt5_password` nunca en logs; no usar `print(settings)` ni `logging.debug(settings.model_dump())`
