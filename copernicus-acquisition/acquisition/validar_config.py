"""Valida el archivo de configuración: python -m acquisition.validar_config [ruta]"""

from __future__ import annotations

import sys

from .config import ConfigError, cargar


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    ruta = argv[0] if argv else "config/adquisicion.yaml"
    try:
        cfg = cargar(ruta, raiz_datos="no-se-usa-en-la-validacion")
    except ConfigError as exc:
        print(f"ERROR en {ruta}: {exc}")
        return 1
    print(f"OK: {ruta} · {len(cfg.zonas)} zonas · {len(cfg.productos)} productos · sha256 {cfg.sha256[:12]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
