"""
Lector directo del Data Lake curated de market_data_hub (MDH), sin pasar por HTTP.

Usado por los flujos de "Datos" (events, informative, probabilistic,
conditioning-count) que no requieren que el proceso MDH esté corriendo:
Event_Edge lee el parquet ya materializado en disco. Si el dataset no
existe, se lanza LakeDatasetNotFoundError para que el router informe al
usuario que debe descargarlo primero vía MDH — no se dispara ingesta
automática aquí.

Price Action sigue usando MdhClient (HTTP) y mantiene su comportamiento
de auto-ingesta, ya que ese flujo sí puede requerir el proceso MDH vivo.

Convención de paths (replica DataLakeWriter._build_dir en market_data_hub):
    {lake_root}/curated/{source}/ohlcv/{asset_class}/{symbol}/{timeframe}/{type_saved}/df.parquet
    {lake_root}/curated/{source}/fundamental/earnings/{asset_class}/{symbol}/quarterly/{type_saved}/df.parquet
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

_OHLCV_COLUMNS = ["open", "high", "low", "close", "volume"]
_EARNINGS_COLUMNS = ["eps_actual", "eps_estimate", "surprise_pct", "revenue_actual", "revenue_estimate"]

_EARNINGS_RAW_COLUMN_MAP = {
    "eps estimate": "eps_estimate",
    "reported eps": "eps_actual",
    "surprise(%)": "surprise_pct",
    "revenue actual": "revenue_actual",
    "revenue estimate": "revenue_estimate",
    "reporttime": "report_time",
}


class LakeDatasetNotFoundError(Exception):
    """El dataset solicitado no existe en el Data Lake curated."""

    def __init__(self, path: Path, symbol: str, source: str) -> None:
        self.path = path
        self.symbol = symbol
        self.source = source
        super().__init__(
            f"No se encontró el dataset de {symbol} (fuente={source}) en el lake. "
            f"Ruta esperada: {path}. Descárgalo primero desde MDH."
        )


def empty_earnings_df() -> pd.DataFrame:
    df = pd.DataFrame(columns=_EARNINGS_COLUMNS)
    df.index = pd.DatetimeIndex([], tz="UTC", name="date")
    return df


def _ohlcv_dir(
    lake_root: str,
    source: str,
    asset_class: str,
    symbol: str,
    timeframe: str,
    type_saved: str = "complete_historical",
) -> Path:
    return (
        Path(lake_root)
        / "curated"
        / source.lower()
        / "ohlcv"
        / asset_class.lower()
        / symbol.upper()
        / timeframe.lower()
        / type_saved
    )


def _earnings_dir(
    lake_root: str,
    source: str,
    asset_class: str,
    symbol: str,
    type_saved: str = "complete_historical",
) -> Path:
    return (
        Path(lake_root)
        / "curated"
        / source.lower()
        / "fundamental"
        / "earnings"
        / asset_class.lower()
        / symbol.upper()
        / "quarterly"
        / type_saved
    )


def _apply_date_filter(
    df: pd.DataFrame,
    start: datetime | None,
    end: datetime | None,
) -> pd.DataFrame:
    if df.empty:
        return df
    out = df
    if start is not None:
        start_ts = pd.Timestamp(start)
        start_ts = start_ts.tz_localize("UTC") if start_ts.tzinfo is None else start_ts.tz_convert("UTC")
        out = out[out.index >= start_ts]
    if end is not None:
        end_ts = pd.Timestamp(end)
        end_ts = end_ts.tz_localize("UTC") if end_ts.tzinfo is None else end_ts.tz_convert("UTC")
        out = out[out.index <= end_ts]
    return out


def read_ohlcv(
    lake_root: str,
    symbol: str,
    source: str,
    asset_class: str,
    timeframe: str = "1d",
    start: datetime | None = None,
    end: datetime | None = None,
) -> pd.DataFrame:
    """
    Lee OHLCV complete_historical directamente del lake curated.

    Retorna DataFrame indexado por fecha UTC con columnas
    [open, high, low, close, volume]. Lanza LakeDatasetNotFoundError si
    el parquet no existe.
    """
    dest_dir = _ohlcv_dir(lake_root, source, asset_class, symbol, timeframe)
    files = list(dest_dir.glob("*.parquet"))
    if not files:
        raise LakeDatasetNotFoundError(dest_dir / "df.parquet", symbol, source)

    df = pd.read_parquet(files[0])
    missing = [c for c in ["date"] + _OHLCV_COLUMNS if c not in df.columns]
    if missing:
        raise LakeDatasetNotFoundError(files[0], symbol, source)

    df["date"] = pd.to_datetime(df["date"], utc=True, errors="coerce")
    df = df.dropna(subset=["date"]).set_index("date")
    df = df[_OHLCV_COLUMNS].astype(float)
    df.sort_index(inplace=True)
    return _apply_date_filter(df, start, end)


def read_earnings(
    lake_root: str,
    symbol: str,
    source: str,
    asset_class: str = "equity",
    start: datetime | None = None,
    end: datetime | None = None,
) -> pd.DataFrame:
    """
    Lee earnings complete_historical directamente del lake curated.

    Retorna DataFrame indexado por fecha UTC con columnas
    [eps_actual, eps_estimate, surprise_pct, revenue_actual, revenue_estimate],
    mismo shape que backend.data.mdh_client.empty_earnings_df(). La última fila
    de cada dataset suele traer eps_estimate poblado y eps_actual/surprise_pct en
    NaN — es el próximo reporte aún no publicado (estimado a futuro).

    Retorna DataFrame vacío si el dataset no existe (a diferencia de OHLCV, la
    ausencia de earnings no bloquea el flujo — algunos símbolos no las tienen).
    """
    dest_dir = _earnings_dir(lake_root, source, asset_class, symbol)
    files = list(dest_dir.glob("*.parquet"))
    if not files:
        return empty_earnings_df()

    raw = pd.read_parquet(files[0])
    if "date" not in raw.columns:
        return empty_earnings_df()

    normalized_cols = {str(c).strip().lower(): c for c in raw.columns}
    rename = {
        normalized_cols[raw_name]: target
        for raw_name, target in _EARNINGS_RAW_COLUMN_MAP.items()
        if raw_name in normalized_cols
    }
    df = raw.rename(columns=rename)

    for col in _EARNINGS_COLUMNS:
        if col not in df.columns:
            df[col] = float("nan")

    df["date"] = pd.to_datetime(df["date"], utc=True, errors="coerce")
    df = df.dropna(subset=["date"])

    # Deduplicar fechas de reporte duplicadas (visto en alphavantage): quedarse
    # con la fila que trae report_time no nulo, o la última si ninguna lo trae.
    if "report_time" in df.columns:
        df = df.assign(_has_report_time=df["report_time"].notna())
        df = df.sort_values(by=["date", "_has_report_time"]).drop(columns="_has_report_time")
    df = df.drop_duplicates(subset=["date"], keep="last")

    df = df.set_index("date")[_EARNINGS_COLUMNS]
    df.sort_index(ascending=False, inplace=True)
    return _apply_date_filter(df, start, end)
