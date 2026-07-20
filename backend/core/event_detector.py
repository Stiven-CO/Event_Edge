"""
Utilidades de alineación earnings → sesión de trading.

Consumidas por feature_builder.py (build_from_fundamental_context) y por
conditioning_pipeline.py (select_raw_events) — punto único de definición de
"a qué día de trading pertenece un reporte de earnings".

Assumptions:
    - ohlcv_df tiene index DatetimeIndex UTC, sin gaps de trading days
    - earnings_df tiene index DatetimeIndex UTC y columnas:
        eps_actual, eps_estimate, revenue_actual, revenue_estimate
"""
from __future__ import annotations

from datetime import time, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from backend.core.utc import to_utc_index

_NY_TZ = ZoneInfo("America/New_York")
_MARKET_CLOSE = time(16, 0)  # 16:00 ET


def resolve_earnings_effective_date(report_ts: pd.Timestamp) -> pd.Timestamp:
    """
    Resuelve la fecha (medianoche UTC) a partir de la cual se busca la sesión
    de trading para un reporte de earnings.

    Si la hora local (ET) del reporte es posterior al cierre de mercado
    (16:00 ET), el evento se desplaza al día calendario siguiente antes del
    forward-fill de sesión (BMO / horario normal no cambian).
    """
    local = pd.Timestamp(report_ts).tz_convert(_NY_TZ)
    effective_date = local.date()
    if local.time() > _MARKET_CLOSE:
        effective_date = effective_date + timedelta(days=1)
    return pd.Timestamp(effective_date, tz=_NY_TZ).tz_convert("UTC")


def _map_earnings_to_trading(
    earnings_df: pd.DataFrame,
    ohlcv_df: pd.DataFrame,
) -> dict[pd.Timestamp, dict]:
    """
    Mapea cada fecha de earnings a la sesión de trading más cercana >= earnings_date.

    Retorna dict {trading_date: {eps_actual, eps_estimate, revenue_actual, revenue_estimate}}.
    Fechas sin sesión disponible o fuera del rango OHLCV se omiten.
    Duplicados se resuelven avanzando a la siguiente fecha de trading libre.
    """
    if earnings_df.empty or ohlcv_df.empty:
        return {}

    trading_dates = to_utc_index(ohlcv_df.index).normalize().sort_values()
    used_dates: set[pd.Timestamp] = set()
    mapping: dict[pd.Timestamp, dict] = {}

    for earnings_ts, row in earnings_df.sort_index(ascending=True).iterrows():
        earnings_ts = resolve_earnings_effective_date(earnings_ts)
        candidates = trading_dates[trading_dates >= earnings_ts]
        if candidates.empty:
            continue

        mapped_date = candidates[0]
        if mapped_date in used_dates:
            remaining = [d for d in candidates[candidates > mapped_date] if d not in used_dates]
            if not remaining:
                continue
            mapped_date = remaining[0]

        used_dates.add(mapped_date)
        mapping[mapped_date] = {
            "eps_actual": row.get("eps_actual"),
            "eps_estimate": row.get("eps_estimate"),
            "surprise_pct": row.get("surprise_pct"),   # Surprise(%) de yfinance (en %)
            "revenue_actual": row.get("revenue_actual"),
            "revenue_estimate": row.get("revenue_estimate"),
        }

    return mapping


def _map_earnings_to_effective_dates(earnings_df: pd.DataFrame) -> dict[pd.Timestamp, dict]:
    """
    Mapea cada fecha de earnings a su fecha efectiva (resolve_earnings_effective_date),
    SIN requerir que exista un día de trading disponible para esa fecha en el OHLCV.

    A diferencia de _map_earnings_to_trading (que descarta reportes sin sesión de
    trading disponible aún — p.ej. el próximo reporte estimado, más reciente que el
    último dato OHLCV cargado), esta función conserva todos los reportes. Es la base
    para el backward/forward-fill expandido (eps_actual_ffill, eps_estimate_ffill,
    etc.), que debe reflejar el último estimado conocido incluso cuando ese reporte
    todavía no tiene una barra OHLCV asociada — replica pd.merge_asof operando sobre
    el DataFrame fundamental completo, tal como en el notebook de referencia.

    Retorna dict {fecha_efectiva: {eps_actual, eps_estimate, surprise_pct,
    revenue_actual, revenue_estimate}}, ordenable por fecha.
    """
    if earnings_df.empty:
        return {}

    mapping: dict[pd.Timestamp, dict] = {}
    for earnings_ts, row in earnings_df.sort_index(ascending=True).iterrows():
        effective_date = resolve_earnings_effective_date(earnings_ts)
        mapping[effective_date] = {
            "eps_actual": row.get("eps_actual"),
            "eps_estimate": row.get("eps_estimate"),
            "surprise_pct": row.get("surprise_pct"),
            "revenue_actual": row.get("revenue_actual"),
            "revenue_estimate": row.get("revenue_estimate"),
        }
    return mapping


def _safe_float(value: object) -> float | None:
    """Convierte a float; retorna None si es NaN, None o no convertible."""
    if value is None:
        return None
    try:
        f = float(value)  # type: ignore[arg-type]
        return None if pd.isna(f) else f
    except (TypeError, ValueError):
        return None


def eps_surprise_pct_from_raw(
    surprise_raw: object, eps_actual: object, eps_estimate: object,
) -> float | None:
    """surprise_pct de yfinance viene en %; se normaliza a decimal (0.0452 = 4.52%)."""
    s = _safe_float(surprise_raw)
    if s is not None:
        return s / 100.0
    a = _safe_float(eps_actual)
    e = _safe_float(eps_estimate)
    if a is not None and e is not None and e != 0:
        return (a - e) / abs(e)
    return None
