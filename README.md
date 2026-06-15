# Event Edge

Una herramienta de estudio probabilístico del mercado diseñada para identificar y validar ventajas estadísticas (*edges*) alrededor de eventos recurrentes.

**Event Edge** forma parte del ecosistema **EdgeStocks** en estrecha colaboración con `market_data_hub`.
* **`market_data_hub` (MDH):** API centralizada que gestiona la ingesta completa y directa para datos no existentes en el ecosistema, o provee acceso de baja latencia al `data_lake` para datos ya normalizados y validados.

---

## Arquitectura de Flujo y Casos de Uso

El flujo de trabajo típico de un trader cuantitativo dentro de **Event Edge** se divide en las siguientes etapas consecutivas:

```text
  ┌────────────────────────┐
  │  1. Selección de Data  │ ──► Verifica en Data Lake / MDH API
  └────────────────────────┘
              │
              ▼
  ┌────────────────────────┐
  │ 2. Métricas Globales   │ ──► Retornos, Volatilidad, Sesgo (Sin Condicionar)
  └────────────────────────┘
              │
              ▼
  ┌────────────────────────┐
  │ 3. Condicionamiento    │ ──► Tendencia, Momentum, Fundamentales, Estacionalidad
  └────────────────────────┘
              │
              ▼
  ┌────────────────────────┐
  │ 4. Análisis Avanzado   │ ──► Modelos Estadísticos + Deep Dive en Price Action
  └────────────────────────┘

```

### 1. Parametrización e Ingesta Automatizada

El analista define las propiedades base del activo desde la Interfaz de Usuario (IU): símbolo, tipo de datos, fuente, segmento financiero y rango temporal.

* **Configuración por defecto:** `timeframe: "1d"` y `type_saved: "complete_historical"`.
* **Lógica Core:** El sistema comprueba primero la presencia local de los archivos en la ruta jerárquica: `datalake/{layer}/{source}/{type_data}/{asset_class}/{symbol}/{timeframe}/{type_saved}/`. Si los datos requeridos están ausentes, **Event Edge** consume de forma automática la API de `market_data_hub` para lanzar un job de ingesta inmediato.

### 2. Métricas Estadísticas Informativas Globales

Antes de aplicar filtros temporales o disparar eventos, el trader calcula la línea base de comportamiento del activo mediante métricas globales no condicionadas:

* **Distribución de Retornos:** Análisis de frecuencias de rendimientos diarios (Histogramas y gráficos Q-Q).
* **Estadísticas de Tendencia Central y Forma:** Media, mediana, desviación estándar, **Sesgo (Skewness)** y **Curtosis (Kurtosis)** para identificar asimetrías y riesgos de cola ancha (*fat tails*).
* **Perfil de Volatilidad:** Volatilidad histórica anualizada y evolución de rangos verdaderos promedio (ATR).
* **Persistencia y Memoria:** Coeficiente de Hurst o métricas de autocorrelación para evaluar si el activo presenta un comportamiento tendencial o de reversión a la media en su estado natural.

### 3. Agrupación y Condicionamiento de Eventos

El usuario aisla ventanas temporales específicas aplicando filtros avanzados basados en condiciones paramétricas clasificadas en:

* **Tendencia & Momentum:** Cruces de medias móviles (SMA/EMA, ratio entre emas %), posición relativa del precio e indicadores de velocidad como el RSI, MACD, Retornos en N secciones %.
* **Sobreextensión & Volatilidad:** Bandas de Bollinger, desviaciones estándar del precio, expansiones de rango y estructuras de *Gaps* de apertura.
* **Fundamentales:** Ventanas de publicación de reportes financieros (*Earnings*, ingresos corporativos, sorpresas en el EPS).
* **Position Gap - Levels:** Interacción del precio con niveles clave de liquidez, máximos/mínimos históricos, puntos pivote o desbalances de órdenes.
* **Estacionalidad:** Patrones recurrentes por día de la semana, efectos de fin de mes o estacionalidades macro mensuales.

### 4. Análisis Probabilístico y Deep Dive en Price Action

Tras ejecutar las condiciones, se procesan las métricas condicionadas a través de una tabla de rendimientos promedios, desviaciones estándar y gráficos de probabilidad para posibles escenarios tras el evento(Close Return, Gap Fill). El usuario cuenta con la opción de inspeccionar el comportamiento visual exacto del precio:

* **Horizonte de Evento = 0 (Enfoque Intradía):** Diseñado como referencia visual para operadores de scalping y day trading. Grafica la microestructura del movimiento el mismo día del evento.
* *Requisito de datos:* Requiere granularidad fija de **30 minutos** bajada de la ruta `datalake/{layer}/{source}/{type_data}/{asset_class}/{symbol}/30m/specific_event/`. Si este fragmento específico no existe en el almacenamiento local, se invoca de inmediato a MDH para extraer y procesar la ventana temporal exacta de dicho evento.


* **Horizonte de Evento > 0 (Enfoque Swing/Posición):** Enfocado en traders de mediano y largo plazo. Muestra la evolución temporal del precio en días o semanas posteriores al evento utilizando el histórico diario (`1d`) previamente consolidado.

---

## Modelos Estadísticos Disponibles

Una vez segmentadas las ventanas del evento, **Event Edge** evalúa la robustez matemática del *edge* mediante cuatro enfoques:

1. **Frequentist (Frecuentista):** Métricas tradicionales de probabilidad, medias muestrales y pruebas de hipótesis estándar ($p$-values).
2. **Bootstrap:** Remuestreo iterativo con reemplazo para calcular intervalos de confianza robustos y mitigar el sesgo de muestras pequeñas.
3. **KDE (Kernel Density Estimation):** Estimación no paramétrica de la función de densidad de probabilidad para visualizar la verdadera distribución de los retornos sin asumir normalidad.
4. **Bayesian (Bayesiano):** Modelado probabilístico que actualiza las distribuciones *a priori* de los retornos con los datos observados del evento, permitiendo un manejo de la incertidumbre superior en entornos financieros ruidosos.

---

## Requisitos del Sistema

* **Backend:** Python 3.11+
* **Frontend:** Node.js 18+
* **Gestor de Entornos:** Anaconda / Miniconda (Entorno recomendado: `event_edge`)

---

## Instalación

```bash
# Clone e instalación del entorno Backend
conda create -n event_edge python=3.11 -y
conda activate event_edge
pip install -e ".[dev]"

# Instalación de dependencias del Frontend
cd frontend
npm install

```

---

## Despliegue y Pruebas E2E

Para ejecutar de forma local la suite completa verificada en las pruebas *End-to-End*:

```powershell
# Servidor Backend (Servicio disponible en puerto :8100)
.\start_server.ps1

# Interfaz de Usuario Frontend (En una terminal independiente)
cd frontend
npm run dev -- --host 0.0.0.0 --port 3000

```

* **Documentación Interactiva de la API:** Disponible en `http://localhost:8100/docs` (Swagger UI).

### Mapeo de Puertos Validado (E2E)

* **Event Edge Backend:** `http://localhost:8100`
* **Event Edge Frontend:** `http://localhost:3000`
* **Market Data Hub (Dependencia Externa Core):** `http://localhost:8080/api/v1`

---

## Integración y Variables de Entorno

El sistema mapea las conexiones externas a través del archivo `.env` ubicado en la raíz del proyecto.

### Fuentes de Datos Soportadas

| Fuente | Tipo de Uso | Variables de Configuración |
| --- | --- | --- |
| `market_data_hub` | Ingesta de OHLCV, Datos Fundamentales y Estados de Conectores (`mt5`, `yfinance`, `AlphaVantage`). | `EE_MDH_BASE_URL`, `EE_MDH_ENABLED`, `EE_MDH_API_KEY` |

### Plantilla de Configuración `.env`

```env
# Configuración de la Dependencia MDH
EE_MDH_BASE_URL=http://localhost:8080/api/v1
EE_MDH_ENABLED=true
EE_MDH_API_KEY=your_mdh_api_key_here

# Entorno de Desarrollo
EE_DEBUG=false

```

*(Para consultar el catálogo completo de variables del sistema, revise el módulo interno `backend/config.py`).*

---

## Pruebas de Software (Testing)

La suite utiliza `pytest` segmentando las ejecuciones para optimizar los pipelines de integración:

```bash
# Ejecutar exclusivamente la suite de tests unitarios (Aislados y sin llamadas externas)
pytest tests/unit/ -v -m unit

# Ejecutar tests de integración (Requiere que el backend esté arriba en http://localhost:8100)
pytest tests/integration/ -v -m integration

```

### Endpoints Verificados en el Proceso E2E

* **`GET /api/v1/control/health`** → Monitoreo de estado de salud del backend de Event Edge.
* **`GET /api/v1/control/broker-status`** → Estado de disponibilidad de los conectores a través de la API de MDH.
* **`POST /api/v1/analysis/informative`** → Cálculo y despacho de las métricas informativas globales.
* **`POST /api/v1/analysis/probabilistic`** → Evaluación estadística bajo los 4 modelos (Frecuentista, Bootstrap, KDE, Bayesiano).
* **`POST /api/v1/events/detect`** → Identificación y mapeo de marcas temporales según las condiciones ingresadas.

```