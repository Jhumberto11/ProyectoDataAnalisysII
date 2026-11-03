"""
Cuadro de mando — Brecha digital y pobreza en hogares salvadoreños (EHPM 2025)
Fase II · Visualización interactiva, UX y Data Storytelling

Ejecutar desde la carpeta raíz del repositorio:
    streamlit run dashboard/app.py

Flujo narrativo (Shneiderman: overview → zoom/filter → details on demand):
    1. Diagnóstico            → tarjetas KPI vs. referencia nacional
    2. Patrones y anomalías   → ranking departamental + gradiente por ingreso
    3. Causa raíz             → pobreza × área y brecha urbano/rural
    4. Recomendación          → priorización de departamentos por impacto
    5. Detalle a demanda      → tabla de inspección y descarga

Todos los porcentajes se ponderan con el factor de expansión `fac00`
(se puede desactivar en la barra lateral para ver cifras muestrales).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# ----------------------------------------------------------------------------
# Configuración general
# ----------------------------------------------------------------------------
st.set_page_config(
    page_title="Brecha Digital · EHPM 2025",
    page_icon="📶",
    layout="wide",
    initial_sidebar_state="expanded",
)

RUTA_DATOS = Path(__file__).resolve().parent.parent / "DatosLimpios" / "dataset_Brecha_Digital_Prueba.csv"

# Paleta semántica (validada para daltonismo; ver adenda IEEE, sección V-B).
# El color solo codifica significado; todo lo demás va en gris.
AZUL = "#2a78d6"      # internet / urbano
NARANJA = "#eb6834"   # segunda categoría (rural), foco, seleccion, departamentos críticos
GRIS = "#b4b2ab"      # contexto, sin selección
GRIS_TXT = "#52514e"  # texto secundario y líneas de referencia y computadora
GRIS_TENUE = "#e2e0da"  # segmentos con muestra insuficiente
N_MINIMO = 30          # tamaño muestral mínimo para considerar fiable un segmento

ORDEN_POBREZA = ["No pobre", "Pobreza relativa", "Pobreza extrema"]
ORDEN_ESTADO = ["Internet y computadora", "Solo internet", "Solo computadora", "Ninguno"]

PLOT_CFG = {"displayModeBar": False}


# ----------------------------------------------------------------------------
# Carga y preparación
# ----------------------------------------------------------------------------
def cuantil_ponderado(x: np.ndarray, w: np.ndarray, q: float | list[float]):
    orden = np.argsort(x)
    x, w = x[orden], w[orden]
    acum = (np.cumsum(w) - 0.5 * w) / w.sum()
    return np.interp(q, acum, x)


@st.cache_data(show_spinner="Cargando datos limpios…")
def cargar_datos() -> tuple[pd.DataFrame, list[str]]:
    df = pd.read_csv(RUTA_DATOS, encoding="utf-8-sig")

    estado = np.select(
        [
            (df.INTERNET_SI_NO == 1) & (df.COMPUTADORA_SI_NO == 1),
            (df.INTERNET_SI_NO == 1) & (df.COMPUTADORA_SI_NO == 0),
            (df.INTERNET_SI_NO == 0) & (df.COMPUTADORA_SI_NO == 1),
        ],
        ORDEN_ESTADO[:3],
        default=ORDEN_ESTADO[3],
    )
    df["estado_digital"] = pd.Categorical(estado, ORDEN_ESTADO, ordered=True)
    df["pobreza"] = pd.Categorical(df["pobreza"], ORDEN_POBREZA, ordered=True)
    df["SIN_NINGUNO"] = ((df.INTERNET_SI_NO == 0) & (df.COMPUTADORA_SI_NO == 0)).astype(int)

    # Quintiles de ingreso per cápita ponderados a nivel nacional (con `ingpe`, no el recortado)
    cortes = cuantil_ponderado(df.ingpe.to_numpy(), df.fac00.to_numpy(), [0.2, 0.4, 0.6, 0.8])
    bordes = [-np.inf, *cortes, np.inf]
    etiquetas = [
        f"Q1 (≤ ${cortes[0]:,.0f})",
        f"Q2 (${cortes[0]:,.0f}–{cortes[1]:,.0f})",
        f"Q3 (${cortes[1]:,.0f}–{cortes[2]:,.0f})",
        f"Q4 (${cortes[2]:,.0f}–{cortes[3]:,.0f})",
        f"Q5 (> ${cortes[3]:,.0f})",
    ]
    df["quintil_ingreso"] = pd.cut(df.ingpe, bordes, labels=etiquetas, right=True)
    return df, etiquetas


df_total, ETIQ_QUINTIL = cargar_datos()


# ----------------------------------------------------------------------------
# Métricas (ponderadas o muestrales)
# ----------------------------------------------------------------------------
def peso(d: pd.DataFrame) -> pd.Series:
    return d["fac00"] if st.session_state.get("ponderar", True) else pd.Series(1.0, index=d.index)


def pct(d: pd.DataFrame, col: str) -> float:
    if d.empty:
        return float("nan")
    w = peso(d)
    return float((d[col] * w).sum() / w.sum() * 100)


def resumen_por(d: pd.DataFrame, grupo: list[str]) -> pd.DataFrame:
    """Agrega por `grupo`: % internet, % computadora, % brecha, hogares estimados y n muestral."""
    w = peso(d)
    tmp = d.assign(
        _w=w,
        _wi=d.INTERNET_SI_NO * w,
        _wc=d.COMPUTADORA_SI_NO * w,
        _wb=d.BRECHA_DIGITAL * w,
        _wn=d.SIN_NINGUNO * w,
        _hog=d.fac00,
        _hog_b=d.BRECHA_DIGITAL * d.fac00,
    )
    g = tmp.groupby(grupo, observed=True).agg(
        n=("idboleta", "size"),
        w=("_w", "sum"),
        wi=("_wi", "sum"),
        wc=("_wc", "sum"),
        wb=("_wb", "sum"),
        wn=("_wn", "sum"),
        hogares=("_hog", "sum"),
        hogares_brecha=("_hog_b", "sum"),
    )
    g["pct_internet"] = g.wi / g.w * 100
    g["pct_computadora"] = g.wc / g.w * 100
    g["pct_brecha"] = g.wb / g.w * 100
    g["pct_ninguno"] = g.wn / g.w * 100
    return g.drop(columns=["w", "wi", "wc", "wb", "wn"]).reset_index()


def fmt_n(x: float) -> str:
    return f"{x:,.0f}".replace(",", " ")


def nota_n(n: int) -> str:
    return "" if n >= N_MINIMO else f"<br><b>⚠ Muestra pequeña (n &lt; {N_MINIMO})</b>"


def layout_base(fig: go.Figure, alto: int, **kw) -> go.Figure:
    fig.update_layout(
        height=alto,
        margin=dict(l=10, r=20, t=10, b=10),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(size=13),
        hoverlabel=dict(bgcolor="white", font_size=13, font_color="#0b0b0b"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, title=None),
        dragmode=False,
        **kw,
    )
    fig.update_xaxes(showgrid=False, zeroline=False, showline=False)
    fig.update_yaxes(showgrid=False, zeroline=False, showline=False)
    return fig


# ----------------------------------------------------------------------------
# Barra lateral: filtros globales sincronizados
# ----------------------------------------------------------------------------
FILTROS = ["f_area", "f_region", "f_depto", "f_pobreza", "f_estado", "f_quintil"]


def limpiar_filtros():
    for k in FILTROS:
        st.session_state[k] = []
    st.session_state["sel_deptos"] = []
    st.session_state["graf_ver"] += 1  # nueva clave = selección del gráfico borrada


st.session_state.setdefault("sel_deptos", [])
st.session_state.setdefault("graf_ver", 0)
CLAVE_GRAF = lambda: f"graf_deptos_{st.session_state.graf_ver}"

with st.sidebar:
    st.markdown("### Filtros globales")
    st.caption("Afectan a **todas** las vistas. Vacío = sin filtrar.")

    st.toggle("Ponderar con factor de expansión (fac00)", value=True, key="ponderar",
              help="Activado: cifras representativas de la población. Desactivado: conteos de la muestra.")

    st.markdown("**Territorio**")
    f_area = st.multiselect("Área", ["Urbano", "Rural"], key="f_area", placeholder="Todas")
    f_region = st.multiselect("Región", sorted(df_total.region.unique()), key="f_region", placeholder="Todas")
    deptos_disp = sorted(
        df_total.loc[df_total.region.isin(f_region) if f_region else slice(None), "r004"].unique()
    )
    # Mantener solo departamentos válidos para la región elegida (filtro en cascada)
    st.session_state["f_depto"] = [d for d in st.session_state.get("f_depto", []) if d in deptos_disp]
    f_depto = st.multiselect("Departamento", deptos_disp, key="f_depto", placeholder="Todos")

    st.markdown("**Condición socioeconómica**")
    f_pobreza = st.multiselect("Pobreza", ORDEN_POBREZA, key="f_pobreza", placeholder="Todas")
    f_quintil = st.multiselect("Quintil de ingreso per cápita", ETIQ_QUINTIL, key="f_quintil", placeholder="Todos")

    st.markdown("**Estado digital del hogar**")
    f_estado = st.multiselect("Acceso", ORDEN_ESTADO, key="f_estado", placeholder="Todos")

    st.button("↺ Restablecer filtros", on_click=limpiar_filtros, width="stretch")

    st.divider()
    st.caption(
        "**Fuente:** EHPM 2025 (DIGESTYC), 17 909 hogares. "
        "Datos de corte transversal: no hay dimensión temporal, por lo que el filtrado "
        "se hace por territorio, condición socioeconómica y estado digital."
    )


def aplicar(d: pd.DataFrame, incluir_seleccion: bool = True) -> pd.DataFrame:
    m = pd.Series(True, index=d.index)
    if f_area:
        m &= d.area.isin(f_area)
    if f_region:
        m &= d.region.isin(f_region)
    if f_depto:
        m &= d.r004.isin(f_depto)
    if f_pobreza:
        m &= d.pobreza.isin(f_pobreza)
    if f_quintil:
        m &= d.quintil_ingreso.isin(f_quintil)
    if f_estado:
        m &= d.estado_digital.isin(f_estado)
    if incluir_seleccion and st.session_state.sel_deptos:
        m &= d.r004.isin(st.session_state.sel_deptos)
    return d[m]


# Filtro cruzado: la selección hecha en el gráfico de departamentos se lee
# ANTES de calcular el resto, para que todas las vistas respondan en la misma pasada.
evento_previo = st.session_state.get(CLAVE_GRAF())
if evento_previo is not None:
    puntos = evento_previo.get("selection", {}).get("points", [])
    st.session_state.sel_deptos = sorted({p["y"] for p in puntos if "y" in p})

df_f_sin_sel = aplicar(df_total, incluir_seleccion=False)  # para vistas que muestran la selección
df_f = aplicar(df_total)                                   # para el resto de vistas

# ----------------------------------------------------------------------------
# Encabezado
# ----------------------------------------------------------------------------
st.title("Brecha digital y pobreza en los hogares salvadoreños")
st.markdown(
    "<span style='color:#52514e'>EHPM 2025 · ¿Qué hogares se están quedando fuera de la conectividad, "
    "dónde están y qué explica su exclusión?</span>",
    unsafe_allow_html=True,
)

activos = [
    ("Área", f_area), ("Región", f_region), ("Departamento", f_depto),
    ("Pobreza", f_pobreza), ("Quintil", f_quintil), ("Acceso", f_estado),
    ("Selección en gráfico", st.session_state.sel_deptos),
]
texto_activos = " · ".join(f"**{k}:** {', '.join(map(str, v))}" for k, v in activos if v)
st.caption(("Filtros activos — " + texto_activos) if texto_activos else "Sin filtros: vista nacional.")

if df_f.empty:
    st.warning("La combinación de filtros no deja hogares. Quita algún filtro o pulsa «Restablecer filtros».")
    st.stop()

n_f = len(df_f)
if n_f < N_MINIMO:
    st.warning(f"Solo {n_f} hogares en la muestra con estos filtros: interpreta las cifras con cautela.")

# ----------------------------------------------------------------------------
# 1. DIAGNÓSTICO — Overview first
# ----------------------------------------------------------------------------
st.header("1 · Diagnóstico", divider="gray")

nac = {c: pct(df_total, c) for c in ["INTERNET_SI_NO", "COMPUTADORA_SI_NO", "BRECHA_DIGITAL", "SIN_NINGUNO"]}
sel = {c: pct(df_f, c) for c in nac}
hay_filtro = len(df_f) != len(df_total)


def delta(c: str) -> str | None:
    return f"{sel[c] - nac[c]:+.1f} pp vs. nacional" if hay_filtro else None


med_ing = cuantil_ponderado(df_f.ingpe.to_numpy(), peso(df_f).to_numpy(), 0.5)
med_nac = cuantil_ponderado(df_total.ingpe.to_numpy(), peso(df_total).to_numpy(), 0.5)

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Hogares representados", fmt_n(df_f.fac00.sum()),
          help=f"Suma de fac00. Hogares en la muestra: {fmt_n(n_f)}.")
k2.metric("Con internet", f"{sel['INTERNET_SI_NO']:.1f} %", delta("INTERNET_SI_NO"))
k3.metric("Con computadora", f"{sel['COMPUTADORA_SI_NO']:.1f} %", delta("COMPUTADORA_SI_NO"))
k4.metric("En brecha digital", f"{sel['BRECHA_DIGITAL']:.1f} %", delta("BRECHA_DIGITAL"),
          delta_color="inverse",
          help="Hogar sin internet, sin computadora o sin ambos (definición operacional del proyecto).")
k5.metric("Ingreso per cápita mediano", f"${med_ing:,.0f}",
          f"{med_ing - med_nac:+,.0f} $ vs. nacional" if hay_filtro else None,
          help="Mediana ponderada de `ingpe` (ingreso original, sin recorte).")

# Composición del estado digital: una sola barra apilada al 100 % (longitud, no ángulos)
comp = (
    df_f.assign(_w=peso(df_f))
    .groupby("estado_digital", observed=False)["_w"].sum()
    .reindex(ORDEN_ESTADO).fillna(0)
)
comp_pct = comp / comp.sum() * 100
colores_estado = [AZUL, "#86b6ef", "#f4a37f", NARANJA]
fig_comp = go.Figure()
for estado, valor, color in zip(ORDEN_ESTADO, comp_pct, colores_estado):
    fig_comp.add_bar(
        x=[valor], y=["Hogares"], orientation="h", name=estado,
        marker=dict(color=color, line=dict(color="white", width=2)),
        text=f"{valor:.0f} %" if valor >= 6 else "", textposition="inside",
        insidetextanchor="middle", textfont=dict(color="white" if color in (AZUL, NARANJA) else "#0b0b0b"),
        hovertemplate=f"<b>{estado}</b><br>%{{x:.1f}} % de los hogares<extra></extra>",
    )
layout_base(fig_comp, 110, barmode="stack", showlegend=True)
fig_comp.update_layout(legend_traceorder="normal")
fig_comp.update_xaxes(range=[0, 100], visible=False)
fig_comp.update_yaxes(visible=False)
st.markdown("**¿Cómo se reparten los hogares según su acceso?**")
st.plotly_chart(fig_comp, width="stretch", config=PLOT_CFG)
st.caption(
    f"Solo **{comp_pct.iloc[0]:.0f} %** de los hogares tiene ambos recursos; "
    f"**{comp_pct.iloc[3]:.0f} %** no tiene ninguno."
)

# ----------------------------------------------------------------------------
# 2. PATRONES Y ANOMALÍAS — Zoom & filter
# ----------------------------------------------------------------------------
st.header("2 · Patrones y anomalías", divider="gray")
c_izq, c_der = st.columns([1.15, 1], gap="large")

with c_izq:
    st.markdown("**Brecha digital por departamento**")
    st.caption("Haz clic en una o varias barras (Shift + clic) para filtrar todo el tablero. "
               "Naranja = las 3 tasas más altas; línea punteada = promedio de la vista.")
    dep = resumen_por(df_f_sin_sel, ["r004"]).sort_values("pct_brecha")
    ref = pct(df_f_sin_sel, "BRECHA_DIGITAL")
    seleccion = st.session_state.sel_deptos

    def color_dep(row):
        if seleccion:
            return NARANJA  if row.r004 in seleccion else GRIS
        return NARANJA if row.r004 in top_tasa else GRIS

    top_tasa = set(dep[dep.n >= N_MINIMO].nlargest(3, "pct_brecha").r004)
    # Muestra pequeña → tono atenuado (no se usa opacidad por barra: rompe la selección por clic en Plotly)
    colores = [color_dep(r) if r.n >= N_MINIMO else GRIS_TENUE for r in dep.itertuples()]
    fig_dep = go.Figure(go.Bar(
        x=dep.pct_brecha, y=dep.r004, orientation="h",
        marker=dict(color=colores),
        text=[f"{v:.0f} %" for v in dep.pct_brecha], textposition="outside",
        textfont=dict(color=GRIS_TXT, size=12), cliponaxis=False,
        customdata=np.stack([dep.pct_internet, dep.pct_computadora, dep.hogares_brecha,
                             dep.n, dep.pct_brecha - ref], axis=1),
        hovertext=[nota_n(n) for n in dep.n],
        hovertemplate=(
            "<b>%{y}</b><br>"
            "En brecha: <b>%{x:.1f} %</b> (%{customdata[4]:+.1f} pp vs. promedio)<br>"
            "Con internet: %{customdata[0]:.1f} %<br>"
            "Con computadora: %{customdata[1]:.1f} %<br>"
            "Hogares en brecha (estimados): %{customdata[2]:,.0f}<br>"
            "Hogares en la muestra: %{customdata[3]:,.0f}%{hovertext}<extra></extra>"
        ),
    ))
    fig_dep.add_vline(x=ref, line=dict(color=GRIS_TXT, width=1.5, dash="dot"))
    fig_dep.add_annotation(x=ref, y=1.0, yref="paper", text=f"Promedio {ref:.0f} %",
                           showarrow=False, yanchor="bottom", font=dict(color=GRIS_TXT, size=12))
    layout_base(fig_dep, 470, showlegend=False)
    fig_dep.update_layout(margin=dict(l=10, r=20, t=28, b=10))
    fig_dep.update_xaxes(range=[0, 105], ticksuffix=" %", showgrid=True, gridcolor="rgba(128,128,128,0.15)")
    st.plotly_chart(fig_dep, width="stretch", config=PLOT_CFG,
                    on_select="rerun", selection_mode="points", key=CLAVE_GRAF())

with c_der:
    st.markdown("**Acceso según quintil de ingreso per cápita**")
    st.caption("Internet crece de forma escalonada con el ingreso; la tenencia de computadora apenas cambia.")
    q = resumen_por(df_f, ["quintil_ingreso"])
    q["etiqueta"] = q.quintil_ingreso.astype(str)
    fig_q = go.Figure()
    for col, nombre, color, pos in [("pct_internet", "Internet", AZUL, "top center"),
                                    ("pct_computadora", "Computadora", GRIS_TXT, "bottom center")]:
        fig_q.add_scatter(
            x=q.etiqueta, y=q[col], name=nombre, mode="lines+markers+text",
            line=dict(color=color, width=2.5), marker=dict(size=9, color=color, line=dict(color="white", width=2)),
            text=[f"{v:.0f}%" if i in (0, len(q) - 1) else "" for i, v in enumerate(q[col])],
            textposition=pos, textfont=dict(color=GRIS_TXT, size=12),
            customdata=np.stack([q.n, q.hogares], axis=1),
            hovertemplate=(f"<b>%{{x}}</b><br>{nombre}: <b>%{{y:.1f}} %</b><br>"
                           "Hogares representados: %{customdata[1]:,.0f}<br>"
                           "Muestra: %{customdata[0]:,.0f}<extra></extra>"),
        )
    layout_base(fig_q, 470, hovermode="x unified")
    fig_q.update_yaxes(range=[0, 105], ticksuffix=" %", showgrid=True, gridcolor="rgba(128,128,128,0.15)")
    fig_q.update_xaxes(tickfont=dict(size=11))
    st.plotly_chart(fig_q, width="stretch", config=PLOT_CFG)
    if len(q) >= 2:
        salto = q.pct_internet.iloc[-1] - q.pct_internet.iloc[0]
        st.caption(f"Del quintil más pobre al más rico, el acceso a internet sube **{salto:.0f} pp**.")

# ----------------------------------------------------------------------------
# 3. CAUSA RAÍZ
# ----------------------------------------------------------------------------
st.header("3 · Análisis de causa raíz", divider="gray")
r_izq, r_der = st.columns([1, 1.15], gap="large")

with r_izq:
    st.markdown("**Pobreza × área: ¿se suman las desventajas?**")
    st.caption("% de hogares en brecha digital. Cada barra es un segmento; la longitud compara directamente.")
    pa = resumen_por(df_f, ["pobreza", "area"])
    fig_pa = go.Figure()
    for area, color in [("Urbano", AZUL), ("Rural", NARANJA)]:
        sub = pa[pa.area == area]
        if sub.empty:
            continue
        fig_pa.add_bar(
            x=sub.pobreza.astype(str), y=sub.pct_brecha, name=area,
            marker=dict(color=color, opacity=[1.0 if n >= N_MINIMO else 0.45 for n in sub.n]),
            text=[f"{v:.0f} %" for v in sub.pct_brecha], textposition="outside",
            textfont=dict(color=GRIS_TXT, size=12), cliponaxis=False,
            customdata=np.stack([sub.pct_internet, sub.pct_computadora, sub.hogares_brecha, sub.n], axis=1),
            hovertemplate=(f"<b>%{{x}} · {area}</b><br>En brecha: <b>%{{y:.1f}} %</b><br>"
                           "Con internet: %{customdata[0]:.1f} %<br>Con computadora: %{customdata[1]:.1f} %<br>"
                           "Hogares en brecha: %{customdata[2]:,.0f}<br>Muestra: %{customdata[3]:,.0f}"
                           "<extra></extra>"),
        )
    layout_base(fig_pa, 420, barmode="group", bargap=0.3, bargroupgap=0.08)
    fig_pa.update_yaxes(range=[0, 110], ticksuffix=" %", showgrid=True, gridcolor="rgba(128,128,128,0.15)")
    fig_pa.update_xaxes(categoryorder="array", categoryarray=ORDEN_POBREZA)
    st.plotly_chart(fig_pa, width="stretch", config=PLOT_CFG)

    try:
        mejor = pa[(pa.pobreza == "No pobre") & (pa.area == "Urbano")].pct_brecha.iloc[0]
        peor = pa[(pa.pobreza == "Pobreza extrema") & (pa.area == "Rural")].pct_brecha.iloc[0]
        st.caption(f"Un hogar rural en pobreza extrema tiene **{peor:.0f} %** de probabilidad de estar en brecha, "
                   f"frente a **{mejor:.0f} %** de uno urbano no pobre (**{peor - mejor:.0f} pp** de diferencia).")
    except IndexError:
        pass

with r_der:
    st.markdown("**Distancia urbano–rural en acceso a internet, por departamento**")
    st.caption("Cada línea es la distancia entre ambas áreas; cuanto más larga, mayor desigualdad territorial.")
    ur = resumen_por(df_f_sin_sel, ["r004", "area"]).pivot(index="r004", columns="area",
                                                          values=["pct_internet", "n"])
    if {"Urbano", "Rural"}.issubset(ur.columns.get_level_values(1)):
        ur = ur.dropna()
        ur.columns = [f"{a}_{b}" for a, b in ur.columns]
        ur["gap"] = ur.pct_internet_Urbano - ur.pct_internet_Rural
        ur = ur.sort_values("gap")
        fig_ur = go.Figure()
        for dpt, fila in ur.iterrows():
            resaltar = (not seleccion) or dpt in seleccion
            fig_ur.add_scatter(
                x=[fila.pct_internet_Rural, fila.pct_internet_Urbano], y=[dpt, dpt], mode="lines",
                line=dict(color=GRIS if resaltar else "rgba(180,178,171,0.35)", width=3),
                hoverinfo="skip", showlegend=False,
            )
        alfa = [1.0 if (not seleccion or d in seleccion) else 0.25 for d in ur.index]
        for area, color, col_n in [("Rural", NARANJA, "n_Rural"), ("Urbano", AZUL, "n_Urbano")]:
            fig_ur.add_scatter(
                x=ur[f"pct_internet_{area}"], y=ur.index, mode="markers", name=area,
                marker=dict(size=11, color=color, opacity=alfa, line=dict(color="white", width=2)),
                customdata=np.stack([ur.gap, ur[col_n]], axis=1),
                hovertemplate=(f"<b>%{{y}} · {area}</b><br>Con internet: <b>%{{x:.1f}} %</b><br>"
                               "Distancia urbano–rural: %{customdata[0]:.1f} pp<br>"
                               "Muestra: %{customdata[1]:,.0f}<extra></extra>"),
            )
        layout_base(fig_ur, 420)
        fig_ur.update_xaxes(range=[0, 100], ticksuffix=" %", showgrid=True, gridcolor="rgba(128,128,128,0.15)")
        st.plotly_chart(fig_ur, width="stretch", config=PLOT_CFG)
        top = ur.gap.idxmax()
        st.caption(f"La mayor distancia está en **{top}**: {ur.gap.max():.0f} pp entre zona urbana y rural.")
    else:
        st.info("Esta vista necesita hogares urbanos y rurales: quita el filtro de área para verla.")

# ----------------------------------------------------------------------------
# 4. RECOMENDACIÓN
# ----------------------------------------------------------------------------
st.header("4 · Recomendación", divider="gray")

prio = resumen_por(df_f, ["r004"])
prio = prio[prio.n >= N_MINIMO].copy()
if not prio.empty:
    prio["cuota_brecha"] = prio.hogares_brecha / prio.hogares_brecha.sum() * 100
    prio = prio.sort_values("hogares_brecha", ascending=False)
    top3 = prio.head(3)
    cuota_top3 = top3.cuota_brecha.sum()
    tasa_alta = prio.sort_values("pct_brecha", ascending=False).head(3)

    rec_izq, rec_der = st.columns([1, 1.1], gap="large")
    with rec_izq:
        st.markdown(
            f"""
**Priorizar por impacto absoluto.** {', '.join(top3.r004)} concentran el **{cuota_top3:.0f} %** de los
hogares en brecha de la vista actual (≈ {fmt_n(top3.hogares_brecha.sum())} hogares). Intervenir ahí
llega al mayor número de hogares.

**Focalizar por intensidad.** {', '.join(tasa_alta.r004)} tienen las tasas de brecha más altas
({', '.join(f'{v:.0f} %' for v in tasa_alta.pct_brecha)}): son candidatos a programas de subsidio
o puntos de acceso comunitario.

"""
        )
        pob = resumen_por(df_f, ["pobreza"]).set_index("pobreza")
        if {"No pobre", "Pobreza extrema"}.issubset(pob.index.astype(str)):
            di = pob.loc["No pobre", "pct_internet"] - pob.loc["Pobreza extrema", "pct_internet"]
            dc = pob.loc["No pobre", "pct_computadora"] - pob.loc["Pobreza extrema", "pct_computadora"]
            cuello = "la **conexión a internet**" if di > dc else "la **tenencia de computadora**"
            accion = ("subsidiar el servicio de internet y ampliar cobertura rural"
                      if di > dc else "dotar de equipos a los hogares de los quintiles 1–2")
            st.markdown(
                f"**Atacar el cuello de botella.** Entre hogares no pobres y en pobreza extrema, el acceso a "
                f"internet cae **{di:.0f} pp** y la tenencia de computadora **{dc:.0f} pp**: el freno principal "
                f"es {cuello}. Acción sugerida: {accion}."
            )
        st.caption("Asociaciones descriptivas (EHPM 2025, ponderadas): no demuestran causalidad.")

    with rec_der:
        st.markdown("**Departamentos priorizados por hogares en brecha (estimados)**")
        tabla = top3 if len(prio) <= 3 else prio.head(8)
        tabla = tabla.sort_values("hogares_brecha")
        fig_p = go.Figure(go.Bar(
            x=tabla.hogares_brecha, y=tabla.r004, orientation="h",
            marker=dict(color=[NARANJA if d in set(top3.r004) else GRIS for d in tabla.r004]),
            text=[f"{fmt_n(v)}  ({p:.0f} %)" for v, p in zip(tabla.hogares_brecha, tabla.pct_brecha)],
            textposition="outside", textfont=dict(color=GRIS_TXT, size=12), cliponaxis=False,
            customdata=np.stack([tabla.cuota_brecha, tabla.pct_brecha], axis=1),
            hovertemplate=("<b>%{y}</b><br>Hogares en brecha: <b>%{x:,.0f}</b><br>"
                           "Tasa de brecha: %{customdata[1]:.1f} %<br>"
                           "Cuota del total en brecha: %{customdata[0]:.1f} %<extra></extra>"),
        ))
        layout_base(fig_p, 330, showlegend=False)
        fig_p.update_xaxes(visible=False, range=[0, tabla.hogares_brecha.max() * 1.35])
        st.plotly_chart(fig_p, width="stretch", config=PLOT_CFG)
        st.caption("Etiqueta: hogares estimados en brecha (tasa del departamento). Naranja = top 3 por impacto.")
else:
    st.info("No hay departamentos con muestra suficiente (n ≥ 30) para emitir una recomendación.")

# ----------------------------------------------------------------------------
# 5. DETALLE A DEMANDA
# ----------------------------------------------------------------------------
st.header("5 · Detalle a demanda", divider="gray")

with st.expander("Tabla de inspección por departamento, área y pobreza", expanded=False):
    det = resumen_por(df_f, ["r004", "area", "pobreza"]).rename(columns={
        "r004": "Departamento", "area": "Área", "pobreza": "Pobreza", "n": "Muestra (n)",
        "hogares": "Hogares estimados", "hogares_brecha": "Hogares en brecha",
        "pct_internet": "% internet", "pct_computadora": "% computadora",
        "pct_brecha": "% brecha", "pct_ninguno": "% sin ninguno",
    }).sort_values("Hogares en brecha", ascending=False)
    st.dataframe(
        det, width="stretch", hide_index=True,
        column_config={
            "Hogares estimados": st.column_config.NumberColumn(format="%d"),
            "Hogares en brecha": st.column_config.NumberColumn(format="%d"),
            "% internet": st.column_config.ProgressColumn(format="%.1f %%", min_value=0, max_value=100),
            "% computadora": st.column_config.ProgressColumn(format="%.1f %%", min_value=0, max_value=100),
            "% brecha": st.column_config.ProgressColumn(format="%.1f %%", min_value=0, max_value=100),
            "% sin ninguno": st.column_config.NumberColumn(format="%.1f %%"),
        },
    )
    st.download_button("Descargar tabla (CSV)", det.to_csv(index=False).encode("utf-8-sig"),
                       "detalle_brecha_digital.csv", "text/csv")

with st.expander("Hogares individuales (registros filtrados)", expanded=False):
    cols = ["idboleta", "r004", "area", "region", "pobreza", "ingpe", "quintil_ingreso",
            "estado_digital", "r32309b", "fac00"]
    st.dataframe(df_f[cols].rename(columns={"r004": "departamento", "ingpe": "ingreso_pc",
                                            "r32309b": "n_computadoras"}),
                 width="stretch", hide_index=True, height=320)
    st.caption(f"{fmt_n(len(df_f))} registros.")

with st.expander("Notas metodológicas", expanded=False):
    st.markdown(
        """
- **Brecha digital**: el hogar carece de internet, de computadora o de ambos (definición operacional del proyecto, no indicador oficial).
- **Ponderación**: porcentajes y hogares estimados usan `fac00`. Es una ponderación descriptiva; no se calculan errores estándar.
- **Ingreso**: se usa `ingpe` original. Los quintiles se calculan a nivel nacional con pesos.
- **Muestras pequeñas**: segmentos con n < 30 aparecen atenuados y señalados en el tooltip.
- **Escalas**: todos los ejes de porcentaje empiezan en 0 (sin ejes truncados).
"""
    )
