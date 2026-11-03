# Dashboard — Brecha digital y pobreza (EHPM 2025)

Cuadro de mando interactivo de la Fase II, construido con **Streamlit + Plotly** sobre
`DatosLimpios/dataset_Brecha_Digital_Prueba.csv` (17 909 hogares, ponderado con `fac00`).

## Ejecutar en local

Desde la carpeta raíz del repositorio:

```
pip install -r dashboard/requirements.txt
streamlit run dashboard/app.py
```

Se abre en `http://localhost:8501`.

## Publicar en Streamlit Community Cloud (gratis)

1. Entrar a https://share.streamlit.io con la cuenta de GitHub dueña del repo.
2. **Create app** → *Deploy a public app from GitHub*.
3. Repositorio: `Jhumberto11/ProyectoDataAnalisysII` · Rama: `main` · Archivo principal: `dashboard/app.py`.
4. **Deploy**. Streamlit Cloud instala `dashboard/requirements.txt` y toma el tema de `.streamlit/config.toml`.
5. Copiar el enlace `https://<nombre>.streamlit.app` para la entrega.

Cualquier `git push` a `main` actualiza la app en línea automáticamente.

## Estructura narrativa

| Sección | Tarea visual (Shneiderman) | Gráficos |
|---|---|---|
| 1. Diagnóstico | Overview first | 5 KPI con delta vs. nacional · barra 100 % del estado digital |
| 2. Patrones y anomalías | Zoom & filter | Ranking departamental (clic = filtro cruzado) · acceso por quintil de ingreso |
| 3. Causa raíz | Relate | Pobreza × área · distancia urbano–rural por departamento |
| 4. Recomendación | — | Texto calculado con los datos filtrados · priorización por impacto |
| 5. Detalle a demanda | Details on demand | Tooltips en todos los gráficos · tabla agregada · registros individuales · descarga CSV |

## Interactividad

- **Filtros globales** (barra lateral): área, región, departamento (en cascada con región),
  pobreza, quintil de ingreso y estado digital. Afectan a todas las vistas.
- **Filtro cruzado por clic**: seleccionar barras en el ranking departamental filtra el resto
  del tablero; Shift + clic agrega más departamentos. «Restablecer filtros» borra todo.
- **Ponderación conmutable**: `fac00` activado (cifras poblacionales) o desactivado (muestra).
- **Muestras pequeñas**: segmentos con n < 30 se atenúan y se advierten en el tooltip.

## Decisiones de diseño (resumen para la adenda IEEE)

- Solo canales precisos: **posición y longitud**. Sin pasteles, sin 3D, ejes de porcentaje desde 0.
- Color semántico y mínimo, con un solo significado en todo el tablero: azul = acceso
  (internet, urbano), naranja = alerta (rural, departamentos críticos y priorizados, selección),
  gris = contexto (incluida la computadora). Paleta validada para daltonismo.
- Etiquetas directas selectivas y línea de referencia del promedio en lugar de leyendas extra.
- **Sin variable temporal**: la EHPM 2025 es de corte transversal, por eso el filtro «tiempo» de
  la consigna se sustituye por filtros territoriales y socioeconómicos.
