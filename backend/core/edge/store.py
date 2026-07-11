from __future__ import annotations

import io
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

import pandas as pd

from backend.core.edge.models import RunMeta

_EDGE_FILENAME = "edge.json"
_RETURN_SAMPLES_FILENAME = "return_samples.parquet"


@dataclass
class EdgeSavePaths:
    """Rutas resultantes de un guardado exitoso."""

    dir: Path
    edge_json: Path
    return_samples_path: Path


class EdgeStore(Protocol):
    """Interfaz de persistencia del objeto Edge + muestras de retorno."""

    def save(
        self,
        run_id: str,
        symbol: str,
        timeframe: str,
        edge_payload: dict[str, Any],
        return_samples_close: list[float],
    ) -> EdgeSavePaths: ...

    def load(self, symbol: str, timeframe: str, run_id: str) -> dict[str, Any]: ...

    def list_runs(self, symbol: str, timeframe: str | None = None) -> list[RunMeta]: ...


def _write_atomic(path: Path, data: bytes) -> None:
    """Escribe `data` en `path` de forma atómica (tmp file + os.replace)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.remove(tmp_name)
        except OSError:
            pass
        raise


def _return_samples_to_parquet_bytes(return_samples_close: list[float]) -> bytes:
    df = pd.DataFrame({"return_close": return_samples_close})
    buf = io.BytesIO()
    df.to_parquet(buf, engine="pyarrow", index=False)
    return buf.getvalue()


class FilesystemEdgeStore:
    """
    Implementación de EdgeStore sobre el sistema de archivos local.

    Estructura: {root}/{symbol}/{timeframe}/{run_id}/edge.json + return_samples.parquet
    """

    def __init__(self, root: str | Path):
        self.root = Path(root)

    def _run_dir(self, symbol: str, timeframe: str, run_id: str) -> Path:
        return self.root / symbol / timeframe / run_id

    def save(
        self,
        run_id: str,
        symbol: str,
        timeframe: str,
        edge_payload: dict[str, Any],
        return_samples_close: list[float],
    ) -> EdgeSavePaths:
        run_dir = self._run_dir(symbol, timeframe, run_id)
        run_dir.mkdir(parents=True, exist_ok=True)

        edge_json_path = run_dir / _EDGE_FILENAME
        _write_atomic(edge_json_path, json.dumps(edge_payload, indent=2, default=str).encode("utf-8"))

        return_samples_path = run_dir / _RETURN_SAMPLES_FILENAME
        _write_atomic(return_samples_path, _return_samples_to_parquet_bytes(return_samples_close))

        return EdgeSavePaths(dir=run_dir, edge_json=edge_json_path, return_samples_path=return_samples_path)

    def load(self, symbol: str, timeframe: str, run_id: str) -> dict[str, Any]:
        edge_json_path = self._run_dir(symbol, timeframe, run_id) / _EDGE_FILENAME
        with open(edge_json_path, encoding="utf-8") as f:
            return json.load(f)

    def list_runs(self, symbol: str, timeframe: str | None = None) -> list[RunMeta]:
        symbol_dir = self.root / symbol
        if not symbol_dir.is_dir():
            return []

        timeframe_dirs = [symbol_dir / timeframe] if timeframe else list(symbol_dir.iterdir())

        runs: list[RunMeta] = []
        for tf_dir in timeframe_dirs:
            if not tf_dir.is_dir():
                continue
            for run_dir in tf_dir.iterdir():
                edge_json_path = run_dir / _EDGE_FILENAME
                if not edge_json_path.is_file():
                    continue
                created_at = datetime.fromtimestamp(edge_json_path.stat().st_mtime, tz=timezone.utc)
                runs.append(
                    RunMeta(
                        run_id=run_dir.name,
                        symbol=symbol,
                        timeframe=tf_dir.name,
                        created_at=created_at,
                    )
                )
        return runs
