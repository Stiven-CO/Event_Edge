from __future__ import annotations

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException

from backend.api.schemas import (
	AnalysisRequest,
	ConditioningParams,
	EventType,
	InformativeMetrics,
	InformativeRequest,
	ModelType,
	ProbabilisticResult,
)
from backend.config import Settings, get_settings
from backend.core.event_detector import EventDetector
from backend.core.feature_builder import FeatureBuilder
from backend.core.metrics import compute_informative_metrics, compute_probabilistic_metrics
from backend.core.statistical_models import (
	BaseEventModel,
	BayesianModel,
	BootstrapModel,
	FrequentistModel,
	KDEModel,
)
from backend.data import EarningsLoader, MdhClient, MdhUnavailableError

router = APIRouter(prefix="/api/v1/analysis", tags=["analysis"])


def get_mdh_client(settings: Settings = Depends(get_settings)) -> MdhClient:
	return MdhClient(settings.mdh_base_url, settings.mdh_api_key)


@router.post(
	"/informative",
	response_model=InformativeMetrics,
	summary="Métricas informativas",
	description="Calcula estadísticas descriptivas sobre todos los eventos detectados sin condicionamiento.",
)
async def informative_analysis(
	req: InformativeRequest,
	settings: Settings = Depends(get_settings),
	mdh_client: MdhClient = Depends(get_mdh_client),
) -> InformativeMetrics:
	loader = EarningsLoader()
	detector = EventDetector()

	try:
		ohlcv_df, source_used = await _load_ohlcv(
			symbol=req.symbol,
			source=req.source,
			asset_class=req.asset_class,
			settings=settings,
			mdh_client=mdh_client,
			loader=loader,
		)
		if ohlcv_df.empty:
			raise HTTPException(
				status_code=404,
				detail=f"No OHLCV data available for {req.symbol}",
			)

		events = _detect_events(
			event_type=req.event_type,
			symbol=req.symbol,
			gap_threshold_pct=req.gap_threshold_pct,
			ohlcv_df=ohlcv_df,
			loader=loader,
			detector=detector,
		)

		return compute_informative_metrics(
			ohlcv_df=ohlcv_df,
			events=events,
			periods=req.periods,
			data_source=source_used,
		)
	except HTTPException:
		raise
	except Exception:
		if settings.debug:
			raise
		raise HTTPException(status_code=500, detail="Internal server error")


@router.post(
	"/probabilistic",
	response_model=ProbabilisticResult,
	summary="Métricas probabilísticas",
	description="Calcula escenarios probabilísticos para close_return y gap_fill.",
)
async def probabilistic_analysis(
	req: AnalysisRequest,
	settings: Settings = Depends(get_settings),
	mdh_client: MdhClient = Depends(get_mdh_client),
) -> ProbabilisticResult:
	loader = EarningsLoader()
	detector = EventDetector()
	feature_builder = FeatureBuilder()

	try:
		ohlcv_df, source_used = await _load_ohlcv(
			symbol=req.symbol,
			source=req.source,
			asset_class=req.asset_class,
			settings=settings,
			mdh_client=mdh_client,
			loader=loader,
		)
		if ohlcv_df.empty:
			raise HTTPException(
				status_code=404,
				detail=f"No OHLCV data available for {req.symbol}",
			)

		events = _detect_events(
			event_type=req.event_type,
			symbol=req.symbol,
			gap_threshold_pct=req.gap_threshold_pct,
			ohlcv_df=ohlcv_df,
			loader=loader,
			detector=detector,
		)

		features_df = feature_builder.build(ohlcv_df, events)
		conditioned_df = apply_conditioning(features_df, req.conditioning)

		model = _build_model(req.model)
		return compute_probabilistic_metrics(
			events_df=conditioned_df,
			ohlcv_df=ohlcv_df,
			model=model,
			model_type=req.model,
			n_periods=req.n_periods,
			bins=req.bins,
			symbol=req.symbol,
			data_source=source_used,
		)
	except HTTPException:
		raise
	except Exception:
		if settings.debug:
			raise
		raise HTTPException(status_code=500, detail="Internal server error")


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
	if cond.return_5d_min is not None:
		f = f[f["return_5d"] >= cond.return_5d_min]
	if cond.return_5d_max is not None:
		f = f[f["return_5d"] <= cond.return_5d_max]
	if cond.return_20d_min is not None:
		f = f[f["return_20d"] >= cond.return_20d_min]
	if cond.return_20d_max is not None:
		f = f[f["return_20d"] <= cond.return_20d_max]
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
	if cond.eps_surprise_pct_min is not None:
		f = f[f["eps_surprise_pct"] >= cond.eps_surprise_pct_min]
	if cond.eps_surprise_pct_max is not None:
		f = f[f["eps_surprise_pct"] <= cond.eps_surprise_pct_max]
	if cond.guidance_directions:
		allowed = {g.value for g in cond.guidance_directions}
		f = f[f["guidance"].map(lambda x: getattr(x, "value", x)).isin(allowed)]

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


def _build_model(model_type: ModelType) -> BaseEventModel:
	if model_type == ModelType.frequentist:
		return FrequentistModel()
	if model_type == ModelType.bootstrap:
		return BootstrapModel()
	if model_type == ModelType.kde:
		return KDEModel()
	if model_type == ModelType.bayesian:
		return BayesianModel()
	return BootstrapModel()


async def _load_ohlcv(
	symbol: str,
	source: str,
	asset_class: str,
	settings: Settings,
	mdh_client: MdhClient,
	loader: EarningsLoader,
) -> tuple[pd.DataFrame, str]:
	if settings.mdh_enabled:
		try:
			df = await mdh_client.query_ohlcv(
				symbol=symbol,
				source=source,
				asset_class=asset_class,
				timeframe="1d",
			)
			return df, "mdh"
		except MdhUnavailableError:
			pass

	return loader.fetch_ohlcv(symbol, period="5y", interval="1d"), "yfinance"


def _detect_events(
	event_type: EventType,
	symbol: str,
	gap_threshold_pct: float,
	ohlcv_df: pd.DataFrame,
	loader: EarningsLoader,
	detector: EventDetector,
):
	earnings_df = loader.fetch_earnings_dates(symbol)
	if event_type == EventType.earnings:
		events = detector.detect_earnings(ohlcv_df, earnings_df)
	else:
		earnings_dates = earnings_df.index.to_pydatetime().tolist()
		events = detector.detect_gaps(
			ohlcv_df,
			threshold_pct=gap_threshold_pct,
			earnings_dates=earnings_dates,
		)
	return [e.model_copy(update={"symbol": symbol}) for e in events]
