import streamlit as st
import pandas as pd
from pathlib import Path
from datetime import timedelta
import geopandas as gpd
import pydeck as pdk
import plotly.express as px

st.set_page_config(page_title="Hydrométrie du Gabon - DGE", layout="wide")

st.markdown("""
<style>
.last-box {background:linear-gradient(135deg,#00b050 0%,#007a33 100%); color:white; border-radius:14px; padding:18px 22px; margin-bottom:14px}
.kpi-box {background:#f8f9fa; border:1px solid #e9ecef; border-radius:12px; padding:12px; text-align:center}
.kpi-val {font-size:22px; font-weight:700; color:#007a33}
.kpi-label {font-size:13px; color:#666}
</style>
""", unsafe_allow_html=True)

st.title("Hydrométrie du Gabon : Direction Générale de l'Eau")

BASE = Path(__file__).parent
RELEVES = BASE / "Releves.csv"
STATIONS_NOMS = {"1141902405":"Mandilou Aviation","1141900112":"Saint-Martin"}

# --- CHARGEMENT RAPIDE ---
@st.cache_data(show_spinner=False)
def load_gis():
    data = {}
    try:
        if (BASE / "Limite_Gabon.shp").exists():
            gdf = gpd.read_file(BASE / "Limite_Gabon.shp", engine="pyogrio")
            if gdf.crs: gdf = gdf.to_crs(4326)
            gdf.columns = [c.lower() for c in gdf.columns]
            data["limite"] = gdf
    except: pass
    try:
        if (BASE / "Rivieres_Gabon.shp").exists():
            gdf = gpd.read_file(BASE / "Rivieres_Gabon.shp", engine="pyogrio")
            if gdf.crs: gdf = gdf.to_crs(4326)
            gdf.columns = [c.lower() for c in gdf.columns]
            # OPTIMISATION : simplification pour chargement rapide
            gdf["geometry"] = gdf.geometry.simplify(0.01, preserve_topology=True)
            data["rivieres"] = gdf
    except: pass
    try:
        if (BASE / "Stations.shp").exists():
            gdf = gpd.read_file(BASE / "Stations.shp", engine="pyogrio")
            if gdf.crs: gdf = gdf.to_crs(4326)
            gdf.columns = [c.lower() for c in gdf.columns]
            data["stations"] = gdf
    except: pass
    return data

@st.cache_data(show_spinner=False)
def load_releves():
    df = pd.read_csv(RELEVES, sep=';', encoding='utf-8-sig', engine='python')
    df.columns = [c.lower().strip() for c in df.columns]
    df["station"] = df["station"].astype(str).str.strip()
    df["capteur"] = df["capteur"].astype(str).str.strip().str.zfill(4)
    df["datetime"] = pd.to_datetime(df["date"].astype(str)+" "+df["heure"].astype(str), dayfirst=True, errors='coerce')
    df["valeur"] = pd.to_numeric(df["valeur"].astype(str).str.replace(',','.'), errors='coerce')
    df = df.dropna(subset=["datetime","valeur"])
    return df

gis = load_gis()

if not RELEVES.exists():
    st.error("Releves.csv introuvable")
    st.stop()

df = load_releves()

# --- 1. FILTRES ---
col_f1, col_f2, col_f3 = st.columns(3)
with col_f1:
    def fmt_station(code):
        return "🌍 Toutes les stations" if code=="Toutes" else f"{code} - {STATIONS_NOMS.get(code, code)}"
    sel_station = st.selectbox("📍 Choisir station", ["Toutes"] + sorted(df["station"].unique().tolist()), format_func=fmt_station)
with col_f2:
    all_params = sorted(df["parametre"].dropna().unique().tolist())
    default_idx = next((i for i,p in enumerate(all_params) if "niveau" in p.lower()), 0)
    sel_param = st.selectbox("📈 Paramètre", all_params, index=default_idx)
with col_f3:
    sel_periode = st.selectbox("🗓️ Période", ["Toutes", "7 jours", "30 jours", "Année"], index=0)

df_f = df[df["parametre"] == sel_param].copy()
if sel_station != "Toutes":
    df_f = df_f[df_f["station"] == sel_station]
if sel_periode != "Toutes" and not df_f.empty:
    last_date = df_f["datetime"].max()
    if sel_periode == "7 jours": df_f = df_f[df_f["datetime"] >= last_date - timedelta(days=7)]
    elif sel_periode == "30 jours": df_f = df_f[df_f["datetime"] >= last_date - timedelta(days=30)]
    elif sel_periode == "Année": df_f = df_f[df_f["datetime"] >= last_date - timedelta(days=365)]

# --- 2. CARTE + 3. TABLEAU DE BORD ---
col_gauche, col_droite = st.columns([1.1, 1.4], gap="large")

with col_gauche:
    layers = []
    if "limite" in gis:
        for geom in gis["limite"].geometry:
            if geom.geom_type == "Polygon":
                layers.append(pdk.Layer("PolygonLayer", data=[{"poly": [list(geom.exterior.coords)]}], get_polygon="poly", get_fill_color=[0,176,80,15], get_line_color=[0,80,0,200], line_width_min_pixels=2))
            elif geom.geom_type == "MultiPolygon":
                for g in geom.geoms:
                    layers.append(pdk.Layer("PolygonLayer", data=[{"poly": [list(g.exterior.coords)]}], get_polygon="poly", get_fill_color=[0,176,80,15], get_line_color=[0,80,0,200], line_width_min_pixels=2))
    if "rivieres" in gis:
        lines = [{"path": list(g.coords)} for g in gis["rivieres"].geometry if g.geom_type=="LineString"]
        if lines:
            layers.append(pdk.Layer("PathLayer", data=lines, get_path="path", get_color=[0,110,255,140], width_min_pixels=2))
    
    pts_all, pts_sel = [], []
    if "stations" in gis:
        for _, r in gis["stations"].iterrows():
            try:
                lat, lon = r.geometry.y, r.geometry.x
                code = str(r.iloc[0])
                for c in r.index:
                    if "code" in str(c).lower() or "station" in str(c).lower():
                        code = str(r[c]); break
                item = {"lat": lat, "lon": lon, "name": f"{code} - {STATIONS_NOMS.get(code, code)}", "code": code}
                if sel_station != "Toutes" and code == sel_station: pts_sel.append(item)
                else: pts_all.append(item)
            except: pass
        if pts_all:
            layers.append(pdk.Layer("ScatterplotLayer", data=pts_all, get_position='[lon, lat]', get_color='[255,0,0,180]', get_radius=6000, radius_min_pixels=5, pickable=True))
        if pts_sel:
            layers.append(pdk.Layer("ScatterplotLayer", data=pts_sel, get_position='[lon, lat]', get_color='[0,176,80,255]', get_radius=12000, radius_min_pixels=10, pickable=True))

    view = pdk.ViewState(latitude=pts_sel[0]["lat"], longitude=pts_sel[0]["lon"], zoom=9) if pts_sel else pdk.ViewState(latitude=-0.8, longitude=11.8, zoom=5.8)
    deck = pdk.Deck(layers=layers, initial_view_state=view, map_style="light", tooltip={"text": "{name}"})
    st.pydeck_chart(deck, height=600)

with col_droite:
    st.subheader("📊 Tableau de bord")
    if df_f.empty:
        st.warning("Pas de données")
    else:
        df_f_sorted = df_f.sort_values("datetime")
        last_row = df_f_sorted.iloc[-1]
        st.markdown(f'<div class="last-box"><div style="font-size:13px;opacity:0.8">Dernière mesure - {STATIONS_NOMS.get(str(last_row["station"]), last_row["station"])} / {last_row["parametre"]}</div><div style="font-size:28px;font-weight:800">{last_row["valeur"]}</div><div style="opacity:0.8">{last_row["date"]} {last_row["heure"]}</div></div>', unsafe_allow_html=True)
        
        c_k1, c_k2, c_k3, c_k4 = st.columns(4)
        v_min, v_max, v_moy = df_f["valeur"].min(), df_f["valeur"].max(), df_f["valeur"].mean()
        with c_k1: st.markdown(f'<div class="kpi-box"><div class="kpi-label">Min</div><div class="kpi-val">{v_min:.2f}</div></div>', unsafe_allow_html=True)
        with c_k2: st.markdown(f'<div class="kpi-box"><div class="kpi-label">Max</div><div class="kpi-val">{v_max:.2f}</div></div>', unsafe_allow_html=True)
        with c_k3: st.markdown(f'<div class="kpi-box"><div class="kpi-label">Moyenne</div><div class="kpi-val">{v_moy:.2f}</div></div>', unsafe_allow_html=True)
        with c_k4:
            if "pluie" in sel_param.lower():
                st.markdown(f'<div class="kpi-box"><div class="kpi-label">Total</div><div class="kpi-val">{df_f["valeur"].sum():.1f} mm</div></div>', unsafe_allow_html=True)
            else:
                st.markdown(f'<div class="kpi-box"><div class="kpi-label">Mesures</div><div class="kpi-val">{len(df_f)}</div></div>', unsafe_allow_html=True)

        fig = px.line(df_f_sorted, x="datetime", y="valeur", title=f"{sel_param} - {sel_station}")
        fig.update_layout(height=380, margin=dict(l=10,r=10,t=40,b=10))
        st.plotly_chart(fig, use_container_width=True)
        try:
            st.download_button("📥 Télécharger PNG", data=fig.to_image(format="png", scale=2), file_name=f"{sel_station}_{sel_param}.png", mime="image/png")
        except: pass
