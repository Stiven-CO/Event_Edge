"""
Construye features de condicionamiento para el análisis probabilístico.

Regla anti-look-ahead:
    Para el evento/barra en fecha T, todos los indicadores se calculan usando
    datos hasta T-1 inclusive (cierre previo).

Clusters:
    A - Tendencia:      ema5_vs_ema20_ratio, price_vs_ema50_pct, trend_direction
    B - Momentum:       return_5d, return_20d, rsi14
    C - Sobreextensión: bb_position, bb_width_pct, rsi14_zone
    D - Volatilidad:    hist_vol_10d, vol_ratio_10_30, atr_pct, vol_regime
    E - Fundamental:    eps_surprise_pct, guidance  (solo path earnings)
    F - Posicionamiento: gap_pct
    G - Estacionalidad: day_of_week, month, quarter, earnings_season

Dependencias: pandas, numpy, ta
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import ta

from backend.api.schemas import (
    BBPosition,
    DayOfWeek,
    EarningsSeason,
    EventRecord,
    EventType,
    GuidanceDirection,
    MonthOfYear,
    Quarter,
    RSIZone,
    TrendDirection,
    VolRegime,
)

_RESULT_COLUMNS = [
    "date", "event_type", "symbol",
    # F - Posicionamiento (raw del evento)
    "gap_pct",
    # A - Tendencia
    "ema5_vs_ema20_ratio", "price_vs_ema50_pct", "trend_direction",
    # B - Momentum
    "return_5d", "return_20d", "rsi14",
    # C - Sobreextensión
    "bb_position", "bb_width_pct", "rsi14_zone",
    # D - Volatilidad
    "hist_vol_10d", "vol_ratio_10_30", "atr_pct", "vol_regime",
    # E - Fundamental
    "eps_surprise_pct", "guidance",
    # G - Estacionalidad
    "day_of_week", "month", "quarter", "earnings_season",
]


class FeatureBuilder:

    def build(
        self,
        ohlcv_df: pd.DataFrame,
        events: list[EventRecord],
    ) -> pd.DataFrame:
        """
        Retorna DataFrame con _RESULT_COLUMNS, una fila por evento.
        Eventos sin datos suficientes → NaN en features técnicos (no se excluyen).
        Todos los indicadores técnicos calculados en T-1 (anti-look-ahead).
        """
        if not events:
            return pd.DataFrame(columns=_RESULT_COLUMNS)

        df = ohlcv_df.sort_index()

        # ── Pre-computar series de indicadores sobre todo el OHLCV ──────────
        s_ema5_vs_ema20 = self._calc_ema5_vs_ema20_ratio(df)
        s_price_vs_ema50 = self._calc_price_vs_ema50_pct(df)
        s_trend_dir = self._calc_trend_direction(df)
        s_return_5d = self._calc_return_nd(df, 5)
        s_return_20d = self._calc_return_nd(df, 20)
        s_rsi14 = self._calc_rsi(df, 14)
        s_bb_position, s_bb_width = self._calc_bb_features(df)
        s_hist_vol_10d = self._calc_hist_vol(df, 10)
        s_hist_vol_30d = self._calc_hist_vol(df, 30)
        s_atr_pct = self._calc_atr_pct(df, 14)

        # Percentiles de vol_10d sobre la serie completa para vol_regime
        vol10_vals = s_hist_vol_10d.dropna()
        vol10_p33 = float(vol10_vals.quantile(0.33)) if len(vol10_vals) > 0 else 0.0
        vol10_p66 = float(vol10_vals.quantile(0.66)) if len(vol10_vals) > 0 else 0.0

        rows: list[dict] = []
        for event in events:
            ts = pd.Timestamp(event.date).tz_convert("UTC")

            rsi14_val = _get_series_value(s_rsi14, ts)
            hist_vol = _get_series_value(s_hist_vol_10d, ts)
            hist_vol30 = _get_series_value(s_hist_vol_30d, ts)

            # RSI zone
            rsi14_zone: RSIZone | None = None
            if rsi14_val is not None:
                if rsi14_val < 30:
                    rsi14_zone = RSIZone.oversold
                elif rsi14_val > 70:
                    rsi14_zone = RSIZone.overbought
                else:
                    rsi14_zone = RSIZone.neutral

            # Vol ratio (10d / 30d)
            vol_ratio: float | None = None
            if hist_vol is not None and hist_vol30 is not None and hist_vol30 != 0:
                vol_ratio = hist_vol / hist_vol30

            # Vol regime (por percentiles de la serie)
            vol_regime: VolRegime | None = None
            if hist_vol is not None:
                if hist_vol <= vol10_p33:
                    vol_regime = VolRegime.low
                elif hist_vol <= vol10_p66:
                    vol_regime = VolRegime.normal
                else:
                    vol_regime = VolRegime.high

            # Estacionalidad
            day_of_week = _ts_to_day_of_week(ts)
            month = _ts_to_month(ts)
            quarter = _ts_to_quarter(ts)
            earnings_season = _ts_to_earnings_season(ts)

            row: dict = {
                "date": ts,
                "event_type": event.event_type,
                "symbol": event.symbol,
                "gap_pct": event.gap_pct,
                # A - Tendencia
                "ema5_vs_ema20_ratio": _get_series_value(s_ema5_vs_ema20, ts),
                "price_vs_ema50_pct": _get_series_value(s_price_vs_ema50, ts),
                "trend_direction": _get_series_value(s_trend_dir, ts),
                # B - Momentum
                "return_5d": _get_series_value(s_return_5d, ts),
                "return_20d": _get_series_value(s_return_20d, ts),
                "rsi14": rsi14_val,
                # C - Sobreextensión
                "bb_position": _get_series_value(s_bb_position, ts),
                "bb_width_pct": _get_series_value(s_bb_width, ts),
                "rsi14_zone": rsi14_zone,
                # D - Volatilidad
                "hist_vol_10d": hist_vol,
                "vol_ratio_10_30": vol_ratio,
                "atr_pct": _get_series_value(s_atr_pct, ts),
                "vol_regime": vol_regime,
                # E - Fundamental
                "eps_surprise_pct": event.eps_surprise_pct,
                "guidance": event.guidance,
                # G - Estacionalidad
                "day_of_week": day_of_week,
                "month": month,
                "quarter": quarter,
                "earnings_season": earnings_season,
            }
            rows.append(row)

        return pd.DataFrame(rows, columns=_RESULT_COLUMNS)

    def build_all_bars(
        self,
        ohlcv_df: pd.DataFrame,
        symbol: str = "",
    ) -> pd.DataFrame:
        """
        Retorna DataFrame con _RESULT_COLUMNS, una fila por barra OHLCV.
        El condicionamiento posterior define cuáles barras se analizan como eventos.
        Cluster E (fundamental) siempre vacío — solo disponible en path earnings.
        """
        if ohlcv_df.empty:
            return pd.DataFrame(columns=_RESULT_COLUMNS)

        df = ohlcv_df.sort_index()

        # ── Pre-computar series de indicadores sobre todo el OHLCV ──────────
        s_ema5_vs_ema20  = self._calc_ema5_vs_ema20_ratio(df)
        s_price_vs_ema50 = self._calc_price_vs_ema50_pct(df)
        s_trend_dir      = self._calc_trend_direction(df)
        s_return_5d      = self._calc_return_nd(df, 5)
        s_return_20d     = self._calc_return_nd(df, 20)
        s_rsi14          = self._calc_rsi(df, 14)
        s_bb_position, s_bb_width = self._calc_bb_features(df)
        s_hist_vol_10d   = self._calc_hist_vol(df, 10)
        s_hist_vol_30d   = self._calc_hist_vol(df, 30)
        s_atr_pct        = self._calc_atr_pct(df, 14)

        # gap_pct por barra: (open[t] - close[t-1]) / close[t-1]
        gap_pct_series = (
            (df["open"] - df["close"].shift(1)) / df["close"].shift(1)
        ).fillna(0.0)

        # Percentiles de vol_10d para vol_regime
        vol10_vals = s_hist_vol_10d.dropna()
        vol10_p33 = float(vol10_vals.quantile(0.33)) if len(vol10_vals) > 0 else 0.0
        vol10_p66 = float(vol10_vals.quantile(0.66)) if len(vol10_vals) > 0 else 0.0

        # RSI zone (vectorizado)
        rsi14_zone_series = pd.Series(index=df.index, dtype=object, name="rsi14_zone")
        rsi14_zone_series[s_rsi14 < 30]  = RSIZone.oversold
        rsi14_zone_series[s_rsi14 > 70]  = RSIZone.overbought
        rsi14_zone_series[(s_rsi14 >= 30) & (s_rsi14 <= 70)] = RSIZone.neutral

        # vol_ratio (vectorizado)
        vol_ratio_series = (
            s_hist_vol_10d / s_hist_vol_30d.replace(0.0, np.nan)
        ).rename("vol_ratio_10_30")

        # vol_regime (vectorizado)
        vol_regime_series = pd.Series(index=df.index, dtype=object, name="vol_regime")
        valid_vol = s_hist_vol_10d.notna()
        vol_regime_series[valid_vol & (s_hist_vol_10d <= vol10_p33)]  = VolRegime.low
        vol_regime_series[
            valid_vol & (s_hist_vol_10d > vol10_p33) & (s_hist_vol_10d <= vol10_p66)
        ] = VolRegime.normal
        vol_regime_series[valid_vol & (s_hist_vol_10d > vol10_p66)] = VolRegime.high

        # Estacionalidad (vectorizado)
        day_of_week_series    = pd.Series(
            [_ts_to_day_of_week(ts) for ts in df.index], index=df.index
        )
        month_series          = pd.Series(
            [_ts_to_month(ts) for ts in df.index], index=df.index
        )
        quarter_series        = pd.Series(
            [_ts_to_quarter(ts) for ts in df.index], index=df.index
        )
        earnings_season_series = pd.Series(
            [_ts_to_earnings_season(ts) for ts in df.index], index=df.index
        )

        result = pd.DataFrame(
            {
                "date":                list(df.index),
                "event_type":          EventType.gap,
                "symbol":              symbol,
                "gap_pct":             gap_pct_series.values,
                "ema5_vs_ema20_ratio": s_ema5_vs_ema20.values,
                "price_vs_ema50_pct":  s_price_vs_ema50.values,
                "trend_direction":     s_trend_dir.values,
                "return_5d":           s_return_5d.values,
                "return_20d":          s_return_20d.values,
                "rsi14":               s_rsi14.values,
                "bb_position":         s_bb_position.values,
                "bb_width_pct":        s_bb_width.values,
                "rsi14_zone":          rsi14_zone_series.values,
                "hist_vol_10d":        s_hist_vol_10d.values,
                "vol_ratio_10_30":     vol_ratio_series.values,
                "atr_pct":             s_atr_pct.values,
                "vol_regime":          vol_regime_series.values,
                "eps_surprise_pct":    None,
                "guidance":            GuidanceDirection.not_available,
                "day_of_week":         day_of_week_series.values,
                "month":               month_series.values,
                "quarter":             quarter_series.values,
                "earnings_season":     earnings_season_series.values,
            },
            index=df.index,
        )

        return result[_RESULT_COLUMNS]

    # ── Cluster A — Tendencia ────────────────────────────────────────────────

    def _calc_ema5_vs_ema20_ratio(self, df: pd.DataFrame) -> pd.Series:
        """(EMA5_{T-1} - EMA20_{T-1}) / EMA20_{T-1} × 100"""
        close = df["close"]
        ema5  = ta.trend.ema_indicator(close, window=5,  fillna=False).shift(1)
        ema20 = ta.trend.ema_indicator(close, window=20, fillna=False).shift(1)
        ratio = (ema5 - ema20) / ema20 * 100
        return ratio.replace([np.inf, -np.inf], np.nan).rename("ema5_vs_ema20_ratio")

    def _calc_price_vs_ema50_pct(self, df: pd.DataFrame) -> pd.Series:
        """(close_{T-1} - EMA50_{T-1}) / EMA50_{T-1} × 100"""
        close      = df["close"]
        prev_close = close.shift(1)
        ema50      = ta.trend.ema_indicator(close, window=50, fillna=False).shift(1)
        pct = (prev_close - ema50) / ema50 * 100
        return pct.replace([np.inf, -np.inf], np.nan).rename("price_vs_ema50_pct")

    def _calc_trend_direction(self, df: pd.DataFrame) -> pd.Series:
        """
        Bullish:  EMA5 > EMA20 > EMA50
        Bearish:  EMA5 < EMA20 < EMA50
        Sideways: cualquier otro orden
        """
        close = df["close"]
        ema5  = ta.trend.ema_indicator(close, window=5,  fillna=False).shift(1)
        ema20 = ta.trend.ema_indicator(close, window=20, fillna=False).shift(1)
        ema50 = ta.trend.ema_indicator(close, window=50, fillna=False).shift(1)

        result  = pd.Series(index=df.index, dtype=object, name="trend_direction")
        bullish = (ema5 > ema20) & (ema20 > ema50)
        bearish = (ema5 < ema20) & (ema20 < ema50)
        result[bullish]            = TrendDirection.bullish
        result[bearish]            = TrendDirection.bearish
        result[~bullish & ~bearish] = TrendDirection.sideways
        result[ema50.isna()]       = None
        return result

    # ── Cluster B — Momentum ─────────────────────────────────────────────────

    def _calc_return_nd(self, df: pd.DataFrame, n: int) -> pd.Series:
        """(close_{T-1} - close_{T-1-n}) / close_{T-1-n} × 100"""
        prev   = df["close"].shift(1)
        prev_n = df["close"].shift(1 + n)
        pct    = (prev - prev_n) / prev_n * 100
        return pct.replace([np.inf, -np.inf], np.nan).rename(f"return_{n}d")

    def _calc_rsi(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """RSI(period) calculado en T-1 (anti-look-ahead)."""
        close = df["close"].shift(1)
        return (
            ta.momentum.RSIIndicator(close=close, window=period, fillna=False)
            .rsi()
            .rename(f"rsi{period}")
        )

    # ── Cluster C — Sobreextensión ───────────────────────────────────────────

    def _calc_bb_features(
        self, df: pd.DataFrame
    ) -> tuple[pd.Series, pd.Series]:
        """
        Retorna (bb_position, bb_width_pct).
        BB(20, 2) sobre close; clasifica open_T respecto a bandas_{T-1}.
        bb_width_pct = (upper - lower) / middle × 100
        """
        close  = df["close"]
        open_t = df["open"]
        index  = df.index

        bb = ta.volatility.BollingerBands(close=close, window=20, window_dev=2, fillna=False)
        bb_lower = bb.bollinger_lband().shift(1)
        bb_upper = bb.bollinger_hband().shift(1)
        bb_mid   = bb.bollinger_mavg().shift(1)

        band_range   = bb_upper - bb_lower
        width_series = (band_range / bb_mid * 100).rename("bb_width_pct")

        # Clasificación vectorizada con np.select
        conditions = [
            open_t < bb_lower,
            open_t <= bb_lower + 0.33 * band_range,
            open_t <= bb_upper - 0.33 * band_range,
            open_t <= bb_upper,
        ]
        choices = [
            BBPosition.below_lower,
            BBPosition.in_lower,
            BBPosition.middle,
            BBPosition.in_upper,
        ]
        pos_arr    = np.select(conditions, choices, default=BBPosition.above_upper)
        pos_series = pd.Series(pos_arr, index=index, dtype=object, name="bb_position")

        # Limpiar barras sin datos suficientes
        no_data = bb_lower.isna() | open_t.isna()
        pos_series[no_data]                = None
        width_series[no_data]              = np.nan
        pos_series[band_range <= 0]        = BBPosition.middle
        width_series[band_range <= 0]      = np.nan

        return pos_series, width_series

    # ── Cluster D — Volatilidad ──────────────────────────────────────────────

    def _calc_hist_vol(self, df: pd.DataFrame, window: int) -> pd.Series:
        """Volatilidad histórica anualizada (%) = std(log_ret[-window:]) × √252 × 100, shifteada T-1."""
        log_ret = np.log(df["close"] / df["close"].shift(1))
        hv = log_ret.rolling(window=window, min_periods=window).std() * math.sqrt(252) * 100
        return hv.shift(1).rename(f"hist_vol_{window}d")

    def _calc_atr_pct(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """ATR(period)_{T-1} / close_{T-1} × 100"""
        prev_close = df["close"].shift(1)
        atr = ta.volatility.AverageTrueRange(
            high=df["high"], low=df["low"], close=df["close"],
            window=period, fillna=False,
        ).average_true_range()
        atr_pct = atr / prev_close * 100
        return atr_pct.shift(1).replace([np.inf, -np.inf], np.nan).rename(f"atr_pct_{period}")


# ---------------------------------------------------------------------------
# Helpers de estacionalidad
# ---------------------------------------------------------------------------

_DOW_MAP = {
    0: DayOfWeek.monday,  1: DayOfWeek.tuesday,  2: DayOfWeek.wednesday,
    3: DayOfWeek.thursday, 4: DayOfWeek.friday,
    5: DayOfWeek.saturday, 6: DayOfWeek.sunday,
}

_MONTH_MAP = {
    1: MonthOfYear.jan,  2: MonthOfYear.feb,  3: MonthOfYear.mar,
    4: MonthOfYear.apr,  5: MonthOfYear.may,  6: MonthOfYear.jun,
    7: MonthOfYear.jul,  8: MonthOfYear.aug,  9: MonthOfYear.sep,
    10: MonthOfYear.oct, 11: MonthOfYear.nov, 12: MonthOfYear.dec,
}

_QUARTER_MAP = {1: Quarter.q1, 2: Quarter.q1, 3: Quarter.q1,
                4: Quarter.q2, 5: Quarter.q2, 6: Quarter.q2,
                7: Quarter.q3, 8: Quarter.q3, 9: Quarter.q3,
                10: Quarter.q4, 11: Quarter.q4, 12: Quarter.q4}

_PEAK_MONTHS = {1, 4, 7, 10}


def _ts_to_day_of_week(ts: pd.Timestamp) -> DayOfWeek | None:
    return _DOW_MAP.get(ts.dayofweek)


def _ts_to_month(ts: pd.Timestamp) -> MonthOfYear | None:
    return _MONTH_MAP.get(ts.month)


def _ts_to_quarter(ts: pd.Timestamp) -> Quarter | None:
    return _QUARTER_MAP.get(ts.month)


def _ts_to_earnings_season(ts: pd.Timestamp) -> EarningsSeason:
    return EarningsSeason.peak if ts.month in _PEAK_MONTHS else EarningsSeason.off_season


# ---------------------------------------------------------------------------
# Helper de lectura de series
# ---------------------------------------------------------------------------

def _get_series_value(series: pd.Series, ts: pd.Timestamp) -> object:
    """Retorna el valor de la serie para ts, o None si no existe / es NaN."""
    try:
        val = series.get(ts)
        if val is None:
            return None
        if isinstance(val, float) and math.isnan(val):
            return None
        return val
    except (KeyError, TypeError):
        return None
