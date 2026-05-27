"""
Wrapper de yfinance para earnings metadata y OHLCV fallback.

No usa cache en disco; cada llamada es fresca (yfinance maneja su propio cache).
"""
from __future__ import annotations

import pandas as pd

_EARNINGS_COLUMNS = [
    "eps_actual",
    "eps_estimate",
    "revenue_actual",
    "revenue_estimate",
]
_OHLCV_COLUMNS = ["open", "high", "low", "close", "volume"]


class EarningsLoader:
    def fetch_earnings_dates(
        self, symbol: str, limit: int = 40
    ) -> pd.DataFrame:
        """
        Retorna DataFrame con columnas:
            date (DatetimeIndex UTC), eps_actual, eps_estimate,
            revenue_actual, revenue_estimate

        Usa yfinance: ticker.earnings_dates.
        Si yfinance no retorna datos → DataFrame vacío con las columnas correctas.
        """
        try:
            import yfinance as yf  # noqa: PLC0415

            ticker = yf.Ticker(symbol)
            raw = ticker.earnings_dates

            if raw is None or raw.empty:
                return _empty_earnings_df()

            df = raw.copy()
            df.index = pd.to_datetime(df.index, utc=True, errors="coerce")
            df = df[~df.index.isna()].sort_index(ascending=False)

            # Mapeo de nombres de columnas de yfinance a los esperados
            column_map = {
                "EPS Actual": "eps_actual",
                "EPS Estimate": "eps_estimate",
                "Revenue Actual": "revenue_actual",
                "Revenue Estimate": "revenue_estimate",
            }
            df = df.rename(columns=column_map)

            for col in _EARNINGS_COLUMNS:
                if col not in df.columns:
                    df[col] = float("nan")

            df = df[_EARNINGS_COLUMNS].head(limit)
            df.index.name = "date"
            return df

        except (AttributeError, TypeError, KeyError):
            return _empty_earnings_df()

    def fetch_ohlcv(
        self,
        symbol: str,
        period: str = "5y",
        interval: str = "1d",
    ) -> pd.DataFrame:
        """
        Fallback OHLCV cuando MDH no está disponible.
        Retorna DataFrame con columnas [open, high, low, close, volume]
        e index DatetimeIndex UTC.
        Lanza ValueError si no hay datos para el símbolo.
        """
        import yfinance as yf  # noqa: PLC0415

        raw = yf.download(
            symbol,
            period=period,
            interval=interval,
            auto_adjust=True,
            progress=False,
        )

        if raw is None or raw.empty:
            raise ValueError(f"No OHLCV data for {symbol}")

        df = raw.copy()
        df.columns = [c[0].lower() if isinstance(c, tuple) else c.lower() for c in df.columns]

        for col in _OHLCV_COLUMNS:
            if col not in df.columns:
                raise ValueError(
                    f"Columna '{col}' no encontrada en datos yfinance para {symbol}"
                )

        df = df[_OHLCV_COLUMNS].astype(float)
        df.index = pd.to_datetime(df.index, utc=True, errors="coerce")
        df = df[~df.index.isna()]
        df.index.name = "date"
        df.sort_index(inplace=True)
        return df

    def is_available(self) -> bool:
        """
        Verifica que yfinance esté importable y funcional.
        Retorna True en condiciones normales.
        """
        try:
            import yfinance  # noqa: F401, PLC0415
            return True
        except ImportError:
            return False


def _empty_earnings_df() -> pd.DataFrame:
    """Retorna DataFrame vacío con el esquema correcto de earnings."""
    df = pd.DataFrame(columns=_EARNINGS_COLUMNS)
    df.index = pd.DatetimeIndex([], tz="UTC", name="date")
    return df
