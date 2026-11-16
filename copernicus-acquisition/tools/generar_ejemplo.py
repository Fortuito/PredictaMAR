"""Ejemplo SINTÉTICO de las dos zonas reales del YAML. Nunca consulta Copernicus."""
from pathlib import Path
import sys
from dataclasses import replace
from datetime import datetime, timezone

BASE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(BASE), str(BASE / "tests")]
from acquisition.config import cargar
from acquisition.run import ejecutar
from conftest import ClienteFalso


if __name__ == "__main__":
    destino = Path(sys.argv[1])
    cfg = cargar(BASE / "config/adquisicion.yaml", str(destino))
    cfg = replace(cfg, productos=(cfg.productos[0],))
    destino.mkdir(parents=True, exist_ok=True)
    (destino / "DATOS_SIMULADOS.txt").write_text(
        "Todos los valores son sintéticos (thetao=18 degrees_C). No son mediciones de Pucusana.\n",
        encoding="utf-8")
    manifiesto, _ = ejecutar(cfg, destino, ClienteFalso(),
                             ahora=datetime(2026, 11, 15, 14, 17, tzinfo=timezone.utc),
                             eco=False, dormir=lambda s: None)
    assert manifiesto['resumen_estados']['disponible'] == 2, manifiesto['resumen_estados']
