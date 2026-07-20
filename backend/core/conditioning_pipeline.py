"""
Pipeline 2 — Features + Condicionamiento.

Único punto que decide "qué barras/fechas cuentan como evento" en todo el
sistema. Reemplaza:
  - El endpoint events.py (detección de eventos "crudos" para el popup/preview
    de la sección Datos) — antes duplicaba su propia carga OHLCV+earnings y
    usaba EventDetector.detect_earnings/detect_gaps, un algoritmo paralelo al
    de FeatureBuilder que llegaba al mismo resultado por otro camino.
  - La lógica de condicionamiento que vivía embebida en
    backend/api/routers/analysis.py (apply_conditioning) — movida aquí porque
    es lógica de negocio pura, no debía vivir en un router.

Consumido por: events.py (vía select_raw_events), analysis.py
(conditioning_count/probabilistic, vía build_conditioned_dataset) y
price_action.py (vía build_conditioned_dataset, solo para las fechas
condicionadas — Price Action descarta todo lo demás del dataset).
"""
from __future__ import annotations

from datetime import datetime

import pandas as pd

from backend.api.schemas import ConditioningParams, EventRecord, EventType
from backend.core.feature_builder import FeatureBuilder


def _to_utc(ts: object) -> pd.Timestamp:
    """Convierte a Timestamp UTC tolerando tanto tz-aware como tz-naive."""
    t = pd.Timestamp(ts)
    return t.tz_localize("UTC") if t.tz is None else t.tz_convert("UTC")


def _filter_features_by_date(
    features_df: pd.DataFrame,
    date_start: object,
    date_end: object,
) -> pd.DataFrame:
    """Filtra el DataFrame de features por rango de fechas usando la columna 'date'."""
    if features_df.empty:
        return features_df
    f = features_df.copy()
    if date_start is not None:
        f = f[f["date"] >= _to_utc(date_start)]
    if date_end is not None:
        f = f[f["date"] <= _to_utc(date_end)]
    return f


def build_features(
    ohlcv_df: pd.DataFrame,
    earnings_df: pd.DataFrame,
    event_type: EventType | None,
    symbol: str = "",
    timeframe: str = "1d",
) -> pd.DataFrame:
    """
    Construye el dataset de features (_RESULT_COLUMNS, una fila por barra OHLCV).

    event_type == earnings → build_from_fundamental_context (incluye máscara
    take_earnings + eps_surprise_pct vía merge_asof-equivalente).
    Cualquier otro caso → build_all_bars (cluster E siempre vacío).
    """
    feature_builder = FeatureBuilder()
    if event_type == EventType.earnings:
        return feature_builder.build_from_fundamental_context(
            ohlcv_df, earnings_df, symbol=symbol, timeframe=timeframe
        )
    return feature_builder.build_all_bars(ohlcv_df, symbol=symbol, timeframe=timeframe)


def build_conditioned_dataset(
    ohlcv_df: pd.DataFrame,
    earnings_df: pd.DataFrame,
    event_type: EventType | None,
    conditioning: ConditioningParams,
    symbol: str = "",
    timeframe: str = "1d",
    date_start: datetime | None = None,
    date_end: datetime | None = None,
) -> tuple[pd.DataFrame, int, pd.DataFrame]:
    """
    Pipeline completo: features → filtro de rango de fechas → condicionamiento.

    Retorna (conditioned_df, n_total, features_df) donde n_total es el total de
    filas antes de aplicar `conditioning` (después del filtro de fechas) y
    features_df es el dataset completo pre-condicionamiento (útil para conteos
    como "eventos detectados" que deben reflejar el total, no el filtrado).
    """
    features_df = build_features(ohlcv_df, earnings_df, event_type, symbol, timeframe)
    features_df = _filter_features_by_date(features_df, date_start, date_end)
    n_total = len(features_df)
    conditioned_df = apply_conditioning(features_df, conditioning)
    return conditioned_df, n_total, features_df


def select_raw_events(
    ohlcv_df: pd.DataFrame,
    earnings_df: pd.DataFrame,
    event_type: EventType,
    symbol: str = "",
    gap_threshold_pct: float = 1.0,
    include_earnings_days: bool | None = None,
) -> list[EventRecord]:
    """
    Detección de eventos "crudos" (sin condicionamiento por A-G) para el popup/
    preview de la sección Datos. Reemplaza EventDetector.detect_earnings/detect_gaps.

    earnings → filas donde take_earnings=True.
    gap      → filas con |gap_pct| > threshold; excluye días de earnings salvo
               que include_earnings_days sea True (misma semántica que antes,
               ahora basada en la fecha efectiva de reporte ya resuelta por
               feature_builder, no en la fecha cruda del reporte).
    """
    features_df = FeatureBuilder().build_from_fundamental_context(
        ohlcv_df, earnings_df, symbol=symbol, timeframe="1d"
    )
    if features_df.empty:
        return []

    if event_type == EventType.earnings:
        rows = features_df[features_df["take_earnings"] == True]  # noqa: E712
    else:
        threshold_decimal = gap_threshold_pct / 100.0
        mask = features_df["gap_pct"].abs() > threshold_decimal
        if include_earnings_days is not True:
            mask &= ~features_df["take_earnings"].astype(bool)
        rows = features_df[mask]

    records = [
        EventRecord(
            date=row["date"].to_pydatetime(),
            event_type=event_type,
            symbol=symbol,
            gap_pct=row.get("gap_pct"),
            eps_actual=row.get("eps_actual") if event_type == EventType.earnings else None,
            eps_estimate=row.get("eps_estimate") if event_type == EventType.earnings else None,
            eps_surprise_pct=row.get("eps_surprise_pct") if event_type == EventType.earnings else None,
            revenue_actual=row.get("revenue_actual") if event_type == EventType.earnings else None,
            revenue_estimate=row.get("revenue_estimate") if event_type == EventType.earnings else None,
        )
        for _, row in rows.iterrows()
    ]
    records.sort(key=lambda r: r.date)
    return records


def apply_conditioning(df: pd.DataFrame, cond: ConditioningParams) -> pd.DataFrame:
    """Filtra df aplicando solo los campos no-None de ConditioningParams (7 clusters)."""
    f = df.copy()

    # ── A: Tendencia ─────────────────────────────────────────────────────────
    if cond.ema5_vs_ema20_ratio_min is not None:
        f = f[f["ema5_vs_ema20_ratio"] >= cond.ema5_vs_ema20_ratio_min]
    if cond.ema5_vs_ema20_ratio_max is not None:
        f = f[f["ema5_vs_ema20_ratio"] <= cond.ema5_vs_ema20_ratio_max]
    if cond.price_vs_ema50_pct_min is not None:
        f = f[f["price_vs_ema50_pct"] >= cond.price_vs_ema50_pct_min]
    if cond.price_vs_ema50_pct_max is not None:
        f = f[f["price_vs_ema50_pct"] <= cond.price_vs_ema50_pct_max]
    if cond.trend_directions:
        allowed = {d.value for d in cond.trend_directions}
        f = f[f["trend_direction"].map(lambda x: getattr(x, "value", x)).isin(allowed)]

    # ── B: Momentum ───────────────────────────────────────────────────────────
    if cond.return_5p_min is not None:
        f = f[f["return_5p"] >= cond.return_5p_min]
    if cond.return_5p_max is not None:
        f = f[f["return_5p"] <= cond.return_5p_max]
    if cond.return_20p_min is not None:
        f = f[f["return_20p"] >= cond.return_20p_min]
    if cond.return_20p_max is not None:
        f = f[f["return_20p"] <= cond.return_20p_max]
    if cond.rsi14_min is not None:
        f = f[f["rsi14"] >= cond.rsi14_min]
    if cond.rsi14_max is not None:
        f = f[f["rsi14"] <= cond.rsi14_max]

    # ── C: Sobreextensión ─────────────────────────────────────────────────────
    if cond.bb_positions:
        allowed = {p.value for p in cond.bb_positions}
        f = f[f["bb_position"].map(lambda x: getattr(x, "value", x)).isin(allowed)]
    if cond.bb_width_pct_min is not None:
        f = f[f["bb_width_pct"] >= cond.bb_width_pct_min]
    if cond.bb_width_pct_max is not None:
        f = f[f["bb_width_pct"] <= cond.bb_width_pct_max]
    if cond.rsi14_zones:
        allowed = {z.value for z in cond.rsi14_zones}
        f = f[f["rsi14_zone"].map(lambda x: getattr(x, "value", x)).isin(allowed)]

    # ── D: Volatilidad ────────────────────────────────────────────────────────
    if cond.hist_vol_10d_min is not None:
        f = f[f["hist_vol_10d"] >= cond.hist_vol_10d_min]
    if cond.hist_vol_10d_max is not None:
        f = f[f["hist_vol_10d"] <= cond.hist_vol_10d_max]
    if cond.vol_ratio_min is not None:
        f = f[f["vol_ratio_10_30"] >= cond.vol_ratio_min]
    if cond.vol_ratio_max is not None:
        f = f[f["vol_ratio_10_30"] <= cond.vol_ratio_max]
    if cond.atr_pct_min is not None:
        f = f[f["atr_pct"] >= cond.atr_pct_min]
    if cond.atr_pct_max is not None:
        f = f[f["atr_pct"] <= cond.atr_pct_max]
    if cond.vol_regimes:
        allowed = {r.value for r in cond.vol_regimes}
        f = f[f["vol_regime"].map(lambda x: getattr(x, "value", x)).isin(allowed)]

    # ── E: Fundamental ────────────────────────────────────────────────────────
    if cond.take_earnings is True:
        f = f[f["take_earnings"] == True]  # noqa: E712
    if cond.eps_surprise_pct_min is not None:
        f = f[f["eps_surprise_pct"] >= cond.eps_surprise_pct_min]
    if cond.eps_surprise_pct_max is not None:
        f = f[f["eps_surprise_pct"] <= cond.eps_surprise_pct_max]
    if cond.reported_eps_trend_min is not None:
        f = f[f["reported_eps_trend"].notna() & (f["reported_eps_trend"] >= cond.reported_eps_trend_min)]
    if cond.reported_eps_trend_max is not None:
        f = f[f["reported_eps_trend"].notna() & (f["reported_eps_trend"] <= cond.reported_eps_trend_max)]
    if cond.eps_estimate_trend_min is not None:
        f = f[f["eps_estimate_trend"].notna() & (f["eps_estimate_trend"] >= cond.eps_estimate_trend_min)]
    if cond.eps_estimate_trend_max is not None:
        f = f[f["eps_estimate_trend"].notna() & (f["eps_estimate_trend"] <= cond.eps_estimate_trend_max)]

    # ── F: Posicionamiento ────────────────────────────────────────────────────
    if cond.gap_pct_min is not None:
        f = f[f["gap_pct"] >= cond.gap_pct_min]
    if cond.gap_pct_max is not None:
        f = f[f["gap_pct"] <= cond.gap_pct_max]
    if cond.gap_direction == "positive":
        f = f[f["gap_pct"] > 0]
    elif cond.gap_direction == "negative":
        f = f[f["gap_pct"] < 0]

    # ── G: Estacionalidad ─────────────────────────────────────────────────────
    if cond.days_of_week:
        allowed = {d.value for d in cond.days_of_week}
        f = f[f["day_of_week"].map(lambda x: getattr(x, "value", x)).isin(allowed)]
    if cond.months:
        allowed = {m.value for m in cond.months}
        f = f[f["month"].map(lambda x: getattr(x, "value", x)).isin(allowed)]
    if cond.quarters:
        allowed = {q.value for q in cond.quarters}
        f = f[f["quarter"].map(lambda x: getattr(x, "value", x)).isin(allowed)]
    if cond.earnings_seasons:
        allowed = {s.value for s in cond.earnings_seasons}
        f = f[f["earnings_season"].map(lambda x: getattr(x, "value", x)).isin(allowed)]

    return f
