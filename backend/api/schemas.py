from __future__ import annotations

import re
from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class EventType(str, Enum):
    earnings = "earnings"
    gap = "gap"


class ModelType(str, Enum):
    frequentist = "frequentist"
    bootstrap = "bootstrap"
    kde = "kde"
    bayesian = "bayesian"


class GuidanceDirection(str, Enum):
    raised = "raised"
    maintained = "maintained"
    lowered = "lowered"
    not_available = "not_available"


class BBPosition(str, Enum):
    below_lower = "below_lower"
    in_lower = "in_lower"
    middle = "middle"
    in_upper = "in_upper"
    above_upper = "above_upper"


class TrendDirection(str, Enum):
    bullish = "bullish"
    sideways = "sideways"
    bearish = "bearish"


class RSIZone(str, Enum):
    oversold = "oversold"
    neutral = "neutral"
    overbought = "overbought"


class VolRegime(str, Enum):
    low = "low"
    normal = "normal"
    high = "high"


class DayOfWeek(str, Enum):
    monday = "monday"
    tuesday = "tuesday"
    wednesday = "wednesday"
    thursday = "thursday"
    friday = "friday"


class MonthOfYear(str, Enum):
    jan = "jan"
    feb = "feb"
    mar = "mar"
    apr = "apr"
    may = "may"
    jun = "jun"
    jul = "jul"
    aug = "aug"
    sep = "sep"
    oct = "oct"
    nov = "nov"
    dec = "dec"


class Quarter(str, Enum):
    q1 = "q1"
    q2 = "q2"
    q3 = "q3"
    q4 = "q4"


class EarningsSeason(str, Enum):
    peak = "peak"
    off_season = "off_season"


# ---------------------------------------------------------------------------
# Evento detectado
# ---------------------------------------------------------------------------

class EventRecord(BaseModel):
    """
    Unidad mínima de un evento detectado (earnings o gap).

    date debe ser timezone-aware (UTC). Nunca naive.
    guidance = GuidanceDirection.not_available cuando la info no está disponible.
    """

    date: datetime
    event_type: EventType
    symbol: str
    gap_pct: float | None = None
    eps_actual: float | None = None
    eps_estimate: float | None = None
    eps_surprise_pct: float | None = None
    revenue_actual: float | None = None
    revenue_estimate: float | None = None
    revenue_surprise_pct: float | None = None
    guidance: GuidanceDirection = GuidanceDirection.not_available


# ---------------------------------------------------------------------------
# Condicionamiento
# ---------------------------------------------------------------------------

class ConditioningParams(BaseModel):
    """
    Filtros opcionales para condicionar el análisis probabilístico.
    None en cualquier campo = sin filtro para esa variable.
    Clusters: tendencia | momentum | sobreextensión | volatilidad |
               fundamental | posicionamiento | estacionalidad
    """

    # ── A: Tendencia ──────────────────────────────────────────────────
    ema5_vs_ema20_ratio_min: float | None = None   # (EMA5-EMA20)/EMA20 × 100
    ema5_vs_ema20_ratio_max: float | None = None
    price_vs_ema50_pct_min: float | None = None    # (close-EMA50)/EMA50 × 100
    price_vs_ema50_pct_max: float | None = None
    trend_directions: list[TrendDirection] | None = None

    # ── B: Momentum ───────────────────────────────────────────────────
    return_5d_min: float | None = None             # retorno 5 sesiones antes
    return_5d_max: float | None = None
    return_20d_min: float | None = None            # retorno 20 sesiones antes
    return_20d_max: float | None = None
    rsi14_min: float | None = None                 # RSI(14) en T-1
    rsi14_max: float | None = None

    # ── C: Sobreextensión ─────────────────────────────────────────────
    bb_positions: list[BBPosition] | None = None
    bb_width_pct_min: float | None = None          # (upper-lower)/middle × 100
    bb_width_pct_max: float | None = None
    rsi14_zones: list[RSIZone] | None = None

    # ── D: Volatilidad ────────────────────────────────────────────────
    hist_vol_10d_min: float | None = None          # vol histórica 10d (anualizada %)
    hist_vol_10d_max: float | None = None
    vol_ratio_min: float | None = None             # hist_vol(10d) / hist_vol(30d)
    vol_ratio_max: float | None = None
    atr_pct_min: float | None = None               # ATR(14) / close × 100
    atr_pct_max: float | None = None
    vol_regimes: list[VolRegime] | None = None

    # ── E: Fundamental (solo earnings) ───────────────────────────────
    eps_surprise_pct_min: float | None = None
    eps_surprise_pct_max: float | None = None
    guidance_directions: list[GuidanceDirection] | None = None

    # ── F: Posicionamiento pre-evento ─────────────────────────────────
    gap_pct_min: float | None = None               # gap de apertura del evento
    gap_pct_max: float | None = None
    gap_direction: Literal["positive", "negative", "any"] = "any"

    # ── G: Estacionalidad ────────────────────────────────────────────
    days_of_week: list[DayOfWeek] | None = None
    months: list[MonthOfYear] | None = None
    quarters: list[Quarter] | None = None
    earnings_seasons: list[EarningsSeason] | None = None


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------

_SYMBOL_RE = re.compile(r"^[A-Z]{1,5}$")

_DEFAULT_BINS: list[float] = [-0.05, -0.01, 0.01, 0.05]


class AnalysisRequest(BaseModel):
    """Body para POST /api/v1/analysis/probabilistic."""

    symbol: str
    source: str = "yfinance"
    asset_class: str = "equity"
    event_type: EventType
    gap_threshold_pct: float = Field(default=1.0, ge=0.1, le=20.0)
    n_periods: int = Field(default=5, ge=0, le=60)
    model: ModelType = ModelType.bootstrap
    bins: list[float] = Field(default_factory=lambda: list(_DEFAULT_BINS))
    conditioning: ConditioningParams = Field(default_factory=ConditioningParams)
    date_range_start: datetime | None = None
    date_range_end: datetime | None = None

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, v: str) -> str:
        if not _SYMBOL_RE.match(v):
            raise ValueError(
                f"symbol '{v}' inválido: debe ser entre 1 y 5 letras mayúsculas (A-Z)."
            )
        return v

    @field_validator("bins")
    @classmethod
    def validate_bins(cls, v: list[float]) -> list[float]:
        if len(v) < 2:
            raise ValueError("bins debe tener al menos 2 elementos.")
        if any(b < -1.0 or b > 1.0 for b in v):
            raise ValueError("Todos los valores de bins deben estar entre -1.0 y 1.0.")
        if v != sorted(v) or len(v) != len(set(v)):
            raise ValueError("bins debe estar ordenado estrictamente de menor a mayor.")
        return v


class DetectEventsRequest(BaseModel):
    """Body para POST /api/v1/events/detect."""

    symbol: str
    source: str = "yfinance"
    asset_class: str = "equity"
    event_type: EventType
    gap_threshold_pct: float = Field(default=1.0, ge=0.1, le=20.0)
    date_range_start: datetime | None = None
    date_range_end: datetime | None = None

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, v: str) -> str:
        if not _SYMBOL_RE.match(v):
            raise ValueError(
                f"symbol '{v}' inválido: debe ser entre 1 y 5 letras mayúsculas (A-Z)."
            )
        return v


class InformativeRequest(BaseModel):
    """Body para POST /api/v1/analysis/informative."""

    symbol: str
    source: str = "yfinance"
    asset_class: str = "equity"
    event_type: EventType
    gap_threshold_pct: float = Field(default=1.0, ge=0.1, le=20.0)
    periods: list[int] = Field(default_factory=lambda: [1, 3, 5, 10])

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, v: str) -> str:
        if not _SYMBOL_RE.match(v):
            raise ValueError(
                f"symbol '{v}' inválido: debe ser entre 1 y 5 letras mayúsculas (A-Z)."
            )
        return v


class AssetInfo(BaseModel):
    """Activo disponible para /api/v1/assets."""

    symbol: str
    source: str
    asset_class: str
    timeframe: str


# ---------------------------------------------------------------------------
# Responses — métricas informativas
# ---------------------------------------------------------------------------

class InformativeMetrics(BaseModel):
    """Respuesta para POST /api/v1/analysis/informative."""

    symbol: str
    event_type: EventType
    n_total_events: int
    frequency_per_year: float
    frequency_per_quarter: float
    avg_movement_range: dict[int, dict]  # {n_period: {mean: float, std: float}}
    avg_candle_range: dict[int, dict]    # {n_period: {mean: float, std: float}}
    gap_mean: float | None
    gap_std: float | None
    data_source: str                     # "mdh" | "yfinance"
    # ── P0 (día del evento) ──
    event_day_range_mean: float | None = None   # (high_P0 - low_P0) / close_P0
    event_day_range_std: float | None = None
    event_day_volume_mean: float | None = None  # volumen bruto del día del evento
    event_day_volume_std: float | None = None
    event_day_return_mean: float | None = None  # (close_P0 - open_P0) / open_P0
    event_day_return_std: float | None = None
    # ── Forward returns: P1-Open → Pn-Close ──
    avg_forward_return: dict[int, dict] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Responses — métricas probabilísticas
# ---------------------------------------------------------------------------

class ScenarioBin(BaseModel):
    """Probabilidad e intervalo de confianza para un bin de escenario."""

    label: str            # ej. "< -5%", "-5% a -1%", "> +5%"
    lower: float | None   # None = -∞
    upper: float | None   # None = +∞
    probability: float
    ci_lower: float
    ci_upper: float
    event_count: int


class ProbabilisticFamily(BaseModel):
    """Resultados de una familia de métricas (close_return, gap_fill)."""

    family: str            # "close_return" | "gap_fill"
    n_periods: int
    n_samples_used: int
    n_total_events: int
    warning: str | None    # "insufficient_samples" | "no_gap_events" | None
    scenarios: list[ScenarioBin]


class ProbabilisticResult(BaseModel):
    """Respuesta completa para POST /api/v1/analysis/probabilistic. Siempre 2 familias."""

    symbol: str
    model: ModelType
    data_source: str
    families: list[ProbabilisticFamily]


# ---------------------------------------------------------------------------
# Responses — price action plot
# ---------------------------------------------------------------------------

class PriceActionPoint(BaseModel):
    """Un punto (x, y) de la serie normalizada."""

    x: int    # índice de barra (intraday) o sesión (1 = P1, 2 = P2 …)
    y: float  # precio indexado (100 = referencia)


class PriceActionSeries(BaseModel):
    """Serie promedio + bandas ±1σ opcionales para un grupo (all/win/loss)."""

    points: list[PriceActionPoint]
    band_upper: list[PriceActionPoint] | None  # None si include_bands=False o insuficiente
    band_lower: list[PriceActionPoint] | None


class PriceActionResult(BaseModel):
    """Respuesta para POST /api/v1/analysis/price-action."""

    anchor_mode: Literal["intraday_30min", "daily"]
    n_periods: int
    x_labels: list[str]           # "09:30"…"16:00" para intraday; "P1"…"Pn" para daily
    series_all:  PriceActionSeries
    series_win:  PriceActionSeries
    series_loss: PriceActionSeries
    n_events_all:     int
    n_events_win:     int
    n_events_loss:    int
    n_events_omitted: int         # eventos sin datos de 30min (solo relevante en intraday)
    warning: str | None           # "insufficient_events" | "some_events_omitted" | None


class PriceActionRequest(BaseModel):
    """Body para POST /api/v1/analysis/price-action."""

    symbol: str
    source: str = "yfinance"
    asset_class: str = "equity"
    event_type: EventType
    gap_threshold_pct: float = Field(default=1.0, ge=0.1, le=20.0)
    n_periods: int = Field(default=5, ge=0, le=60)
    include_bands: bool = True
    conditioning: ConditioningParams = Field(default_factory=ConditioningParams)

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, v: str) -> str:
        if not re.compile(r"^[A-Z]{1,5}$").match(v):
            raise ValueError(
                f"symbol '{v}' inválido: debe ser entre 1 y 5 letras mayúsculas (A-Z)."
            )
        return v


# ---------------------------------------------------------------------------
# Control
# ---------------------------------------------------------------------------

class BrokerStatus(BaseModel):
    """Estado de disponibilidad de una fuente de datos."""

    source: str   # "mdh" | "mt5" | "tws" | "yfinance"
    alive: bool
    mode: str     # "primary" | "fallback" | "disabled"
    detail: str | None = None
