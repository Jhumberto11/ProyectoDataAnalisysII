#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Pipeline reproducible de limpieza para Brecha Digital - EHPM 2025

Resumen: 

Entradas:
  1) Base SPSS .sav original (requiere pyreadstat)

Salidas: 
Especificar Ruta en donde se almacenara el dataset limpio

para ejecutar el pipeline se tiene que iniciar desde la terminal con el siguietne


python codigo/limpiar_datos.py \
  --entrada fuente_principal/Base_EHPM_2025.sav \
  --salida DatosLimpios/dataset_Brecha_Digital_Prueba1.csv \
  --reporte documentos/reporte_calidad_prueba.json
python codigo/probar_entrega.py \
  DatosLimpios/dataset_Brecha_Digital_Prueba1.csv

"""

from __future__ import annotations
import argparse
import json
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

BASE = ["idboleta", "fac00", "area", "region", "r004", "pobreza", "ingpe", "r3213a", "r32309a", "r32309b"]
OUT = BASE[:9] + ["r32309b", "INTERNET_SI_NO", "COMPUTADORA_SI_NO", "es_outlier_ingreso", "INGPE_LIMPIO", "BRECHA_DIGITAL", "LOG_INGPE", "INGPE_ESCALADO", "PC_ESCALADO"]
CATEGORICAS = ["area", "region", "r004", "pobreza", "r3213a", "r32309a"]
VALIDOS = {
    "area": {"Urbano", "Rural"},
    "pobreza": {"No pobre", "Pobreza relativa", "Pobreza extrema"},
    "r3213a": {"Sí", "No"},
    "r32309a": {"Sí", "No"},
}


def normalizar_cadena(v):
    if pd.isna(v):
        return pd.NA
    return " ".join(str(v).strip().split())


def sin_acentos(v):
    return "".join(c for c in unicodedata.normalize("NFKD", str(v)) if not unicodedata.combining(c)).lower()


def armonizar_categoricas(df: pd.DataFrame) -> pd.DataFrame:
    for col in CATEGORICAS:
        df[col] = df[col].map(normalizar_cadena).astype("string")
    for col in ("r3213a", "r32309a"):
        norma = df[col].map(lambda x: sin_acentos(x) if pd.notna(x) else "")
        df[col] = norma.map({"si": "Sí", "no": "No"}).astype("string")
    norma = df["area"].map(lambda x: sin_acentos(x) if pd.notna(x) else "")
    df["area"] = norma.map({"urbano": "Urbano", "rural": "Rural"}).astype("string")
    pobreza_map = {"no pobre": "No pobre", "pobreza relativa": "Pobreza relativa", "pobreza extrema": "Pobreza extrema"}
    norma = df["pobreza"].map(lambda x: sin_acentos(x) if pd.notna(x) else "")
    df["pobreza"] = norma.map(pobreza_map).astype("string")
    return df


def cargar(ruta: Path) -> tuple[pd.DataFrame, dict]:
    if ruta.suffix.lower() == ".sav":
        try:
            df = pd.read_spss(ruta)
        except ImportError as exc:
            raise SystemExit("Para leer archivos SPSS se necesita: pip install pyreadstat") from exc
        procedencia = "SPSS original; hay observaciones a nivel de persona que se agregan por hogar"
    elif ruta.suffix.lower() == ".csv":
        df = pd.read_csv(ruta, encoding="utf-8-sig", low_memory=False)
        procedencia = "CSV intermedio de 10 variables; ya contiene una fila por hogar e imputación estructural previa"
    else:
        raise ValueError("La entrada debe ser .csv o .sav")
    df.columns = [c.lower().strip() for c in df.columns]
    faltan = sorted(set(BASE) - set(df.columns))
    if faltan:
        raise ValueError("No están todas las variables requeridas: " + ", ".join(faltan))
    datos = df[BASE].copy()
    return datos, {"fuente": ruta.name, "tipo_fuente": procedencia, "filas_entrada": int(len(datos))}


def pipeline(datos: pd.DataFrame, auditoria: dict) -> tuple[pd.DataFrame, dict]:
    df = datos[BASE].copy()
    for c in ["idboleta", "fac00", "ingpe", "r32309b"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    if df["idboleta"].isna().any():
        raise ValueError("ID de hogar nulo. Revisar el original en lugar de eliminar filas silenciosamente.")
    if ((df["idboleta"] % 1) != 0).any():
        raise ValueError("Se encontraron identificadores de hogar no enteros")
    df["idboleta"] = df["idboleta"].astype("int64")

    # Antes de deduplicar, comprobar que no se pierden discrepancias intrahogar.
    conflictivas = {}
    if df["idboleta"].duplicated().any():
        for c in BASE[1:]:
            conteo = df.groupby("idboleta", sort=False, observed=True)[c].nunique(dropna=False)
            n_conf = int((conteo > 1).sum())
            if n_conf:
                conflictivas[c] = n_conf
        if conflictivas:
            raise ValueError("Hay registros del mismo hogar con valores distintos. Revisar antes de elegir uno: " + str(conflictivas))
    auditoria["filas_repetidas_por_hogar_eliminadas"] = int(df["idboleta"].duplicated().sum())
    df = df.drop_duplicates(subset="idboleta", keep="first").copy()
    auditoria["filas_duplicadas_exactas_eliminadas_adicionalmente"] = 0  # Todas las duplicidades por hogar se resolvieron arriba.
    auditoria["hogares_antes_de_imputacion"] = int(len(df))

    df = armonizar_categoricas(df)
    for c, permitidos in VALIDOS.items():
        invalidos = df[c].notna() & ~df[c].isin(permitidos)
        if invalidos.any():
            raise ValueError(f"En {c} hay valores no contemplados: {df.loc[invalidos,c].value_counts().to_dict()}")

    # Categorías territoriales faltantes: no inventar pertenencias.
    auditoria["faltantes_categorias_antes"] = {c: int(df[c].isna().sum()) for c in CATEGORICAS}
    for c in ["region", "r004"]:
        df[c] = df[c].fillna("No especificado")
    if df[["area", "pobreza", "r3213a", "r32309a"]].isna().any().any():
        raise ValueError("Faltan área, pobreza o respuestas Sí/No. No imputarlas sin evidencia.")

    if df["fac00"].isna().any() or not df["fac00"].gt(0).all():
        raise ValueError("El factor fac00 debe ser numérico y estrictamente positivo.")
    if df["ingpe"].lt(0).any():
        raise ValueError("Se encontraron ingresos per cápita negativos; requieren revisión específica.")
    auditoria["faltantes_ingpe_imputados_mediana"] = int(df["ingpe"].isna().sum())
    med_ing = float(df["ingpe"].median())
    if not np.isfinite(med_ing):
        raise ValueError("No hay ingresos numéricos disponibles para imputación.")
    df["ingpe"] = df["ingpe"].fillna(med_ing)

    df["INTERNET_SI_NO"] = df["r3213a"].map({"Sí": 1, "No": 0}).astype("int64")
    df["COMPUTADORA_SI_NO"] = df["r32309a"].map({"Sí": 1, "No": 0}).astype("int64")

    # Vacío + No computador = cero estructural, nunca mediana.
    faltaba_pc = df["r32309b"].isna()
    cero_estructural = (df["COMPUTADORA_SI_NO"] == 0) & faltaba_pc
    df.loc[cero_estructural, "r32309b"] = 0
    auditoria["faltantes_pc_convertidos_a_cero_estructural"] = int(cero_estructural.sum())
    grupo_si = df["COMPUTADORA_SI_NO"] == 1
    med_pc = df.loc[grupo_si, "r32309b"].median()
    faltantes_en_si = grupo_si & df["r32309b"].isna()
    auditoria["faltantes_pc_si_imputados_mediana"] = int(faltantes_en_si.sum())
    if faltantes_en_si.any():
        if pd.isna(med_pc) or med_pc < 1:
            raise ValueError("No hay mediana válida de cantidad para hogares que tienen computadora.")
        df.loc[faltantes_en_si, "r32309b"] = med_pc
    if df["r32309b"].isna().any():
        raise ValueError("Hay cantidades de computadora faltantes sin regla justificable.")
    if (df["r32309b"].lt(0) | ~np.isclose(df["r32309b"] % 1, 0)).any():
        raise ValueError("Hay cantidades de computadora negativas o no enteras.")
    if ((df["COMPUTADORA_SI_NO"] == 0) & (df["r32309b"] != 0)).any():
        raise ValueError("Se declaran computadoras en hogares que respondieron 'No'.")
    if ((df["COMPUTADORA_SI_NO"] == 1) & (df["r32309b"] <= 0)).any():
        raise ValueError("Se declara tener computadora pero la cantidad es cero.")
    df["r32309b"] = df["r32309b"].astype("int64")

    # IQR sólo como campo AUXILIAR; ingreso original ingpe queda intacto.
    q1, q3 = df["ingpe"].quantile([.25, .75]).tolist()
    iqr = q3 - q1
    inferior, superior = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    df["es_outlier_ingreso"] = (df["ingpe"] < inferior) | (df["ingpe"] > superior)
    df["INGPE_LIMPIO"] = df["ingpe"].clip(lower=max(0.0, inferior), upper=superior)
    df["LOG_INGPE"] = np.log1p(df["INGPE_LIMPIO"])
    df["BRECHA_DIGITAL"] = (~((df["INTERNET_SI_NO"] == 1) & (df["COMPUTADORA_SI_NO"] == 1))).astype("int64")

    def robusto(s: pd.Series):
        p25, p75 = s.quantile([.25, .75]).tolist()
        rango = p75 - p25
        return (s - s.median()) / (rango if rango != 0 else 1.0)
    df["INGPE_ESCALADO"] = robusto(df["INGPE_LIMPIO"])
    df["PC_ESCALADO"] = robusto(df["r32309b"])
    df = df[OUT].sort_values("idboleta", kind="stable").reset_index(drop=True)

    auditoria.update({
        "filas_salida": int(len(df)),
        "columnas_salida": int(len(df.columns)),
        "hogares_unicos": int(df["idboleta"].nunique()),
        "ids_duplicados_final": int(df["idboleta"].duplicated().sum()),
        "nulos_final_total": int(df.isna().sum().sum()),
        "faltantes_por_columna_final": {k: int(v) for k, v in df.isna().sum().items()},
        "ingreso_mediana_imputacion": med_ing,
        "mediana_pc_si_tienen": float(med_pc) if pd.notna(med_pc) else None,
        "limite_ingreso_atipico_inferior": float(inferior),
        "limite_ingreso_atipico_superior": float(superior),
        "ingresos_atipicos_iqr": int(df["es_outlier_ingreso"].sum()),
        "hogares_estimados_fac00": float(df["fac00"].sum()),
        "internet_pct_muestral": float(df["INTERNET_SI_NO"].mean() * 100),
        "internet_pct_ponderado": float(np.average(df["INTERNET_SI_NO"], weights=df["fac00"]) * 100),
        "computadora_pct_ponderado": float(np.average(df["COMPUTADORA_SI_NO"], weights=df["fac00"]) * 100),
        "filas_menor_5000": len(df) < 5000,
    })
    return df, auditoria


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entrada", required=True, type=Path, help="Ruta al CSV intermedio o al .sav original")
    parser.add_argument("--salida", required=True, type=Path, help="Ruta de CSV limpio resultante")
    parser.add_argument("--reporte", type=Path, default=None, help="Ruta JSON para los controles de calidad")
    args = parser.parse_args()
    if not args.entrada.exists():
        raise SystemExit(f"No se encontró la entrada: {args.entrada}")
    base, auditoria = cargar(args.entrada)
    limpio, auditoria = pipeline(base, auditoria)
    args.salida.parent.mkdir(parents=True, exist_ok=True)
    limpio.to_csv(args.salida, index=False, encoding="utf-8-sig", float_format="%.12g")
    if args.reporte:
        args.reporte.parent.mkdir(parents=True, exist_ok=True)
        args.reporte.write_text(json.dumps(auditoria, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"OK: {len(limpio):,} hogares | {len(limpio.columns)} variables | 0 faltantes | 0 ID duplicados")
    print(f"Internet ponderado: {auditoria['internet_pct_ponderado']:.2f}%")
    print(f"CSV listo: {args.salida}")


if __name__ == "__main__":
    main()
