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
from datetime import datetime, timezone

import pandas as pd

from backend.api.schemas import EventRecord, EventType, GuidanceDirection

logger = logging.getLogger(__name__)


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
            earnings_ts = pd.Timestamp(earnings_ts).normalize().tz_convert("UTC")

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
            eps_surprise_pct: float | None = None
            if eps_actual is not None and eps_estimate is not None and eps_estimate != 0:
                eps_surprise_pct = (eps_actual - eps_estimate) / abs(eps_estimate)

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

def _safe_float(value: object) -> float | None:
    """Convierte a float; retorna None si es NaN, None o no convertible."""
    if value is None:
        return None
    try:
        f = float(value)  # type: ignore[arg-type]
        return None if pd.isna(f) else f
    except (TypeError, ValueError):
        return None
