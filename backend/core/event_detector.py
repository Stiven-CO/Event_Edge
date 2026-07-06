"""
Detecta eventos earnings y gap en series OHLCV diarias.

Assumptions:
    - ohlcv_df tiene index DatetimeIndex UTC, sin gaps de trading days
    - Columnas: open, high, low, close, volume (float)
    - OHLCV ajustado (precios post-split)
    - earnings_df tiene index DatetimeIndex UTC y columnas:
        eps_actual, eps_estimate, revenue_actual, revenue_estimate
    - Un evento por fecha: si earnings y gap coinciden, se registra earnings
"""
from __future__ import annotations

import logging
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd

from backend.api.schemas import EventRecord, EventType, GuidanceDirection

logger = logging.getLogger(__name__)

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


class EventDetector:

    def detect_earnings(
        self,
        ohlcv_df: pd.DataFrame,
        earnings_df: pd.DataFrame,
    ) -> list[EventRecord]:
        """
        Alinea fechas de earnings con el DataFrame OHLCV.

        Lógica de alineación:
            1. Para cada fecha de earnings, buscar la fecha de trading más cercana
               en ohlcv_df que sea >= a la fecha de earnings (forward-fill).
            2. Si la fecha mapeada ya fue usada → usar la siguiente disponible.
            3. Calcular gap_pct = (open_T - close_{T-1}) / close_{T-1}
            4. Si no hay sesión previa → excluir el evento.
            5. Earnings fuera del rango OHLCV → excluir sin error.

        Retorna lista de EventRecord con event_type=earnings, ordenada por date asc.
        """
        if ohlcv_df.empty or earnings_df.empty:
            return []

        trading_dates = ohlcv_df.index.normalize().sort_values()
        trading_dates_set: set[pd.Timestamp] = set(trading_dates)

        # close_{T-1} por sesión: shift(1) sobre el índice ordenado
        prev_close = ohlcv_df["close"].shift(1)

        used_dates: set[pd.Timestamp] = set()
        records: list[EventRecord] = []

        # Ordenar earnings de más reciente a más antiguo para procesar por orden
        sorted_earnings = earnings_df.sort_index(ascending=True)

        for earnings_ts, row in sorted_earnings.iterrows():
            earnings_ts = resolve_earnings_effective_date(earnings_ts)

            # Buscar la primera fecha de trading >= earnings_ts
            candidates = trading_dates[trading_dates >= earnings_ts]
            if candidates.empty:
                logger.debug(
                    "Earnings %s fuera del rango OHLCV (después del último dato); excluido",
                    earnings_ts.date(),
                )
                continue

            mapped_date = candidates[0]

            # Evitar duplicados: avanzar hasta la siguiente fecha libre
            if mapped_date in used_dates:
                remaining = candidates[candidates > mapped_date]
                # Filtrar solo las que no están usadas
                free = [d for d in remaining if d not in used_dates]
                if not free:
                    logger.warning(
                        "Earnings duplicados mapeados a %s; no hay fecha libre disponible, ignorando",
                        mapped_date.date(),
                    )
                    continue
                mapped_date = free[0]

            # Necesitamos prev_close
            if mapped_date not in trading_dates_set:
                logger.debug("Fecha mapeada %s no en trading_dates; excluido", mapped_date.date())
                continue

            pc = prev_close.get(mapped_date)
            if pc is None or pd.isna(pc):
                logger.debug(
                    "Sin cierre previo disponible para %s (primera sesión); excluido",
                    mapped_date.date(),
                )
                continue

            open_price = ohlcv_df.loc[mapped_date, "open"]
            gap_pct = (open_price - pc) / pc

            used_dates.add(mapped_date)

            eps_actual = _safe_float(row.get("eps_actual"))
            eps_estimate = _safe_float(row.get("eps_estimate"))
            eps_surprise_pct = eps_surprise_pct_from_raw(
                row.get("surprise_pct"), eps_actual, eps_estimate
            )

            records.append(
                EventRecord(
                    date=mapped_date.to_pydatetime().replace(tzinfo=timezone.utc),
                    event_type=EventType.earnings,
                    symbol="",  # se rellena en capa superior
                    gap_pct=gap_pct,
                    eps_actual=eps_actual,
                    eps_estimate=eps_estimate,
                    eps_surprise_pct=eps_surprise_pct,
                    guidance=GuidanceDirection.not_available,
                )
            )

        records.sort(key=lambda r: r.date)
        return records

    def detect_gaps(
        self,
        ohlcv_df: pd.DataFrame,
        threshold_pct: float = 1.0,
        earnings_dates: list[datetime] | None = None,
    ) -> list[EventRecord]:
        """
        Detecta sesiones donde |gap_pct| > threshold_pct / 100.

        Lógica:
            1. gap_pct = (open_T - close_{T-1}) / close_{T-1}  (decimal, no %)
            2. Filtrar |gap_pct| > threshold_pct / 100
            3. Excluir fechas en earnings_dates
            4. Crear EventRecord con event_type=gap

        Retorna lista ordenada por date asc.
        """
        if ohlcv_df.empty:
            return []

        df = ohlcv_df.copy()
        df = df.sort_index()

        prev_close = df["close"].shift(1)
        gap = (df["open"] - prev_close) / prev_close

        threshold_decimal = threshold_pct / 100.0
        mask = gap.abs() > threshold_decimal
        gap_rows = gap[mask].dropna()

        # Normalizar earnings_dates para comparación
        excluded: set[pd.Timestamp] = set()
        if earnings_dates:
            for dt in earnings_dates:
                excluded.add(pd.Timestamp(dt).normalize().tz_convert("UTC"))

        records: list[EventRecord] = []
        for ts, gap_val in gap_rows.items():
            ts_norm = pd.Timestamp(ts).normalize().tz_convert("UTC")
            if ts_norm in excluded:
                logger.debug(
                    "Gap en %s excluido por coincidir con earnings",
                    ts_norm.date(),
                )
                continue

            records.append(
                EventRecord(
                    date=ts_norm.to_pydatetime().replace(tzinfo=timezone.utc),
                    event_type=EventType.gap,
                    symbol="",  # se rellena en capa superior
                    gap_pct=float(gap_val),
                    guidance=GuidanceDirection.not_available,
                )
            )

        records.sort(key=lambda r: r.date)
        return records


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _map_earnings_to_trading(
    earnings_df: pd.DataFrame,
    ohlcv_df: pd.DataFrame,
) -> dict[pd.Timestamp, dict]:
    """
    Mapea cada fecha de earnings a la sesión de trading más cercana >= earnings_date.

    Retorna dict {trading_date: {eps_actual, eps_estimate, revenue_actual, revenue_estimate}}.
    Fechas sin sesión disponible o fuera del rango OHLCV se omiten.
    Duplicados se resuelven igual que en detect_earnings() (forward-avance a fecha libre).
    """
    if earnings_df.empty or ohlcv_df.empty:
        return {}

    trading_dates = ohlcv_df.index.normalize().sort_values()
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
