#!/usr/bin/env python3
"""Verifica integridad del CSV final. Uso: python codigo/probar_entrega.py resultado/dataset_Brecha_Digital_Proyecto.csv"""
from pathlib import Path
import sys
import pandas as pd
import numpy as np

ruta=Path(sys.argv[1]) if len(sys.argv)>1 else Path('resultado/dataset_Brecha_Digital_Proyecto.csv')
a=pd.read_csv(ruta,encoding='utf-8-sig')
assert len(a)>=5000, 'El dataset no llega a 5,000 hogares'
assert len(a)==a.idboleta.nunique(), 'Existen hogares repetidos'
assert a.shape[1]==18, 'El esquema no contiene exactamente 18 columnas'
assert a.isna().sum().sum()==0, 'Hay celdas vacías'
assert a.fac00.gt(0).all(), 'Factores de expansión inválidos'
assert a.ingpe.ge(0).all(), 'Ingresos negativos'
assert a.INTERNET_SI_NO.isin([0,1]).all()
assert a.COMPUTADORA_SI_NO.isin([0,1]).all()
assert a.BRECHA_DIGITAL.isin([0,1]).all()
assert (a.BRECHA_DIGITAL==(~(a.INTERNET_SI_NO.eq(1)&a.COMPUTADORA_SI_NO.eq(1))).astype(int)).all()
assert ((a.COMPUTADORA_SI_NO.eq(0)&a.r32309b.eq(0))|(a.COMPUTADORA_SI_NO.eq(1)&a.r32309b.ge(1))).all()
assert np.isclose(np.average(a.INTERNET_SI_NO,weights=a.fac00)*100,46.12546611997058,atol=0.01), 'El porcentaje ponderado cambió respecto al dataset de referencia'
print('TODOS LOS CONTROLES OK')
print('Hogares:',format(len(a),','),'| Variables:',len(a.columns),'| Nulos:',int(a.isna().sum().sum()))
print('Internet ponderado:',round(np.average(a.INTERNET_SI_NO,weights=a.fac00)*100,2),'%')
