# Event Edge

Herramienta de estudio probabilístico de eventos **Earnings & Gap** para acciones americanas.

Parte del ecosistema EdgeStocks junto a `Backtest_Forge`, `LiveEdge` y `market_data_hub`.

---

## Descripción

Event Edge permite analizar el comportamiento estadístico del precio alrededor de eventos:
- **Earnings**: resultados trimestrales con sorpresa EPS/revenue y guía de management
- **Gap**: aperturas con gap significativo respecto al cierre anterior

Incluye cuatro modelos estadísticos (Frequentist, Bootstrap, KDE, Bayesian) y condicionamiento
por indicadores técnicos (EMA, Bollinger Bands, dirección del gap).

---

## Requisitos

- Python 3.11+
- Node.js 18+ (para el frontend)
- Entorno conda recomendado: `event_edge`

---

## Instalación

```bash
# Backend
conda create -n event_edge python=3.11 -y
conda activate event_edge
pip install -e ".[dev]"

# Frontend
cd frontend
npm install
```

---

## Arranque

```powershell
# Backend (puerto 8100)
.\start_server.ps1

# Frontend (puerto 5173) — en otra terminal
cd frontend
npm run dev
```

El backend expone la documentación interactiva en `http://localhost:8100/docs`.

---

## Fuentes de datos

| Fuente | Uso | Variable de entorno |
|--------|-----|---------------------|
| market_data_hub | OHLCV primaria | `EE_MDH_BASE_URL`, `EE_MDH_ENABLED` |
| yfinance | OHLCV fallback + Earnings metadata | — |
| MT5 | Fuente de datos de broker | `EE_MT5_LOGIN`, `EE_MT5_SERVER` |
| TWS | Fuente de datos de broker | `EE_TWS_API_KEY` |

Configurar en `.env` (ver `backend/config.py` para todas las variables disponibles).

---

## Variables de entorno

Crear `.env` en la raíz del proyecto:

```env
EE_MDH_BASE_URL=http://localhost:8000/api/v1
EE_MDH_ENABLED=true
EE_DEBUG=false
```

---

## Tests

```bash
# Tests unitarios (sin conexión a brokers)
pytest tests/unit/ -v -m unit

# Tests de integración (requiere servidor en :8100)
pytest tests/integration/ -v -m integration
```
