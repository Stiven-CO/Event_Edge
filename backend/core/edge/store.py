from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from backend.core.edge.models import RunMeta

_EDGE_FILENAME = "edge.json"


@dataclass
class EdgeSavePaths:
    """Rutas resultantes de un guardado exitoso."""

    dir: Path
    edge_json: Path
    plots: dict[str, Path]


class EdgeStore(Protocol):
    """Interfaz de persistencia del objeto Edge + plots asociados."""

    def save(
        self,
        run_id: str,
        symbol: str,
        timeframe: str,
        edge_payload: dict[str, Any],
        plots: dict[str, bytes],
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


class FilesystemEdgeStore:
    """
    Implementación de EdgeStore sobre el sistema de archivos local.

    Estructura: {root}/{symbol}/{timeframe}/{run_id}/edge.json + {plot}.png
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
        plots: dict[str, bytes],
    ) -> EdgeSavePaths:
        run_dir = self._run_dir(symbol, timeframe, run_id)
        run_dir.mkdir(parents=True, exist_ok=True)

        edge_json_path = run_dir / _EDGE_FILENAME
        _write_atomic(edge_json_path, json.dumps(edge_payload, indent=2, default=str).encode("utf-8"))

        plot_paths: dict[str, Path] = {}
        for name, png_bytes in plots.items():
            plot_path = run_dir / f"{name}.png"
            _write_atomic(plot_path, png_bytes)
            plot_paths[name] = plot_path

        return EdgeSavePaths(dir=run_dir, edge_json=edge_json_path, plots=plot_paths)

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
