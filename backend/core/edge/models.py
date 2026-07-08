from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class EdgeEnvelope(BaseModel):
    """
    Sobre de metadata/versionado que envuelve el objeto Edge persistido.

    La estructura interna de `edge` sigue el contenido estadístico definido en
    el plan ("Contenido estadístico del Edge para Risk Engine"); su forma
    externa final (agrupamiento, nombres de nivel superior) se afina en fase
    posterior.
    """

    run_id: str
    symbol: str
    timeframe: str
    created_at: datetime
    conditioning_params: dict[str, Any]
    schema_version: int = 1
    plots: dict[str, str]         # nombre lógico -> ruta relativa del PNG
    edge: dict[str, Any]          # payload estadístico (ver assembler.assemble_edge_payload)


class RunMeta(BaseModel):
    """Metadata resumida de un run persistido, usada por EdgeStore.list_runs."""

    run_id: str
    symbol: str
    timeframe: str
    created_at: datetime
