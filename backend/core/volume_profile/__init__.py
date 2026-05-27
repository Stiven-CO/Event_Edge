"""
Volume Profile Calculator — STUB v1

Interfaz planificada para v2. Sin implementación en v1.

Descripción:
    Calcula el perfil de volumen por rango de precio (VPVR) para una ventana
    de sesiones y reporta la probabilidad de que el precio alcance cada nivel
    basándose en la distribución de volumen histórico.

Interfaz planificada para v2:

    from dataclasses import dataclass

    @dataclass
    class VPVRResult:
        price_levels: list[float]           # niveles de precio
        volume_at_level: list[float]        # volumen en cada nivel
        poc: float                          # Point of Control (máximo volumen)
        value_area_high: float              # límite superior del 70% del volumen
        value_area_low: float               # límite inferior del 70% del volumen
        prob_reach_level: dict[float, float]  # P(precio alcanza nivel)

    class VolumeProfileCalculator:
        def compute(
            self,
            ohlcv_df: pd.DataFrame,
            n_bins: int = 50,
            lookback_sessions: int = 20,
        ) -> VPVRResult:
            '''
            Calcula VPVR para las últimas `lookback_sessions` sesiones.

            Args:
                ohlcv_df: DataFrame OHLCV con index DatetimeIndex UTC
                n_bins: Número de niveles de precio (granularidad del histograma)
                lookback_sessions: Ventana de sesiones a considerar

            Returns:
                VPVRResult con POC, VAH, VAL y probabilidades por nivel

            Raises:
                NotImplementedError: En v1 siempre — implementar en v2
            '''
            raise NotImplementedError("Volume Profile disponible en v2")

Dependencias previstas para v2:
    - OHLCV con timeframe intraday (1m/5m) para mayor precisión
    - Funciona con 1d pero con menor granularidad
    - scipy para histograma ponderado por volumen

Integración planificada con v2:
    - Endpoint: GET /api/v1/analysis/volume-profile?symbol=AAPL&lookback=20
    - Componente frontend: overlay en ProbabilityPanel mostrando POC y VA
    - Parámetros configurables: n_bins, lookback_sessions

Para implementar en v2:
    1. Calcular distribución de volumen por bins de precio (histograma ponderado por vol)
    2. Calcular POC (bin con mayor volumen acumulado)
    3. Calcular Value Area: expandir desde POC hasta cubrir 70% del volumen total
    4. Modelar P(reach_level) como función empírica del volumen relativo al POC
    5. Agregar router en analysis.py y componente VolumeProfileOverlay en frontend
"""

__all__: list[str] = []
