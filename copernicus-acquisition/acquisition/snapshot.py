"""Resumen por variable y área; no representa valores puntuales ni derivados."""


def construir_snapshot(manifiesto):
    variables = []
    for el in manifiesto["elementos"]:
        for variable in el["variables"]:
            estad = el["control"].get(variable, {})
            confiable = el["estado"] in ("disponible", "parcial")
            variables.append({
                "variable": variable, "zona_id": el["zona_id"],
                "dataset_id": el["dataset_id"], "product_id": el["product_id"],
                "dataset_version": el["dataset_version"], "tipo_dato": el["tipo_dato"],
                "ventana_nominal": el["ventana_solicitada"], "cobertura_efectiva": el["cobertura_efectiva"],
                "procesado_utc": el["procesado_utc"], "antiguedad_horas": el["antiguedad_horas"],
                "area_solicitada": el["area_solicitada"], "area_efectiva": el["area_efectiva"],
                "distancia_coordenadas_km": None,
                "profundidad_solicitada_m": el["profundidad_solicitada_m"],
                "niveles_efectivos_m": el["niveles_efectivos_m"],
                "resolucion_efectiva": el["resolucion_efectiva"], "estado": el["estado"], "causa": el["causa"],
                "tratamiento": el["tratamiento"], "unidades": el["unidades"].get(variable),
                "fraccion_validas": estad.get("fraccion_validas"),
                "estadisticas_area_ventana": {k: estad.get(k) if confiable else None for k in ("min", "max", "media")},
                "archivo": el["archivo"], "sha256": el["sha256"],
            })
    return {"schema_version": "1.0", "tipo": "resumen_adquisicion_por_area",
            "run_id": manifiesto["run_id"], "inicio_utc": manifiesto["inicio_utc"],
            "commit": manifiesto["commit"], "version_modulo": manifiesto["version_modulo"],
            "variables": variables}
