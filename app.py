import streamlit as st
import pandas as pd
from pathlib import Path
import geopandas as gpd
import pydeck as pdk
import plotly.express as px

st.set_page_config(page_title="Hydrométrie du Gabon - DGE", layout="wide")
st.title("Hydrométrie du Gabon : Direction Générale de l'Eau")

BASE = Path(__file__).parent
RELEVES = BASE / "Releves.csv"

STATIONS_NOMS = {"1141902405":"Mandilou Aviation","1141900112":"Saint-Martin"}

@st.cache_data
def load_gis():
    data = {}
    if (BASE / "Limite_Gabon.shp").exists():
        try:
            gdf = gpd.read_file(BASE / "Limite_Gabon.shp", engine="pyogrio")
            if gdf.crs: gdf = gdf.to_crs(4326)
            data["limite"] = gdf
        except: pass
    if (BASE / "Rivieres_Gabon.shp").exists():
        try:
            gdf = gpd.read_file(BASE / "Rivieres_Gabon.shp", engine="pyogrio")
            if gdf.crs: gdf = gdf.to_crs(4326)
            data["rivieres"] = gdf
        except: pass
    if (BASE / "Stations.shp").exists():
        try:
            gdf = gpd.read_file(BASE / "Stations.shp", engine="pyogrio")
            if gdf.crs: gdf = gdf.to_crs(4326)
            data["stations"] = gdf
        except: pass
    return data

@st.cache_data
def load_releves():
    if not RELEVES.exists():
        return None
    try:
        df = pd.read_csv(RELEVES, sep=';', encoding='utf-8-sig', errors='ignore')
        # normalisation colonnes
        df.columns = [c.lower().strip() for c in df.columns]
        # station et capteur en string
        if "station" in df.columns:
            df["station"] = df["station"].astype(str).str.strip()
        if "capteur" in df.columns:
            df["capteur"] = df["capteur"].astype(str).str.strip()
        if "date" in df.columns and "heure" in df.columns:
            df["datetime"] = pd.to_datetime(df["date"].astype(str)+" "+df["heure"].astype(str), dayfirst=True, errors='coerce')
        if "valeur" in df.columns:
            df["valeur"] = pd.to_numeric(df["valeur"].astype(str).str.replace(',','.'), errors='coerce')
        return df
    except Exception as e:
        st.error(f"Erreur lecture Releves.csv : {e}")
        return None

gis = load_gis()
df = load_releves()

# --- DEBUG QUE TU VAS VOIR ---
with st.expander("🔍 Debug - Vérification données", expanded=True):
    st.write(f"Releves.csv trouvé ? {RELEVES.exists()} - Taille: {RELEVES.stat().st_size/1024:.1f} Ko" if RELEVES.exists() else "Non trouvé")
    if df is not None:
        st.write("Stations dans Releves.csv:", df["station"].unique().tolist())
        st.write("Nombre lignes Mandilou (1141902405):", len(df[df["station"]=="1141902405"]))
        st.write("Nombre lignes Saint-Martin (1141900112):", len(df[df["station"]=="1141900112"]))
    st.write("Shapefiles chargés:", list(gis.keys()))

# --- CARTE ---
st.subheader("🗺️ Carte Gabon")
layers = []
if "limite" in gis:
    for geom in gis["limite"].geometry:
        if geom and geom.geom_type == "Polygon":
            layers.append(pdk.Layer("PolygonLayer", data=[{"poly": list(geom.exterior.coords)}], get_polygon="poly", get_fill_color=[0,0,0,0], get_line_color=[0,80,0,200], line_width_min_pixels=2))

if "rivieres" in gis:
    lines = [{"path": list(g.coords)} for g in gis["rivieres"].geometry if g and g.geom_type=="LineString"]
    if lines:
        layers.append(pdk.Layer("PathLayer", data=lines, get_path="path", get_color=[0,110,255,150], width_min_pixels=2))

if "stations" in gis:
    pts = []
    for _, r in gis["stations"].iterrows():
        try:
            pts.append({"lat": r.geometry.y, "lon": r.geometry.x, "name": str(r.iloc[0])})
        except: pass
    if pts:
        layers.append(pdk.Layer("ScatterplotLayer", data=pts, get_position='[lon, lat]', get_color='[255,0,0,220]', get_radius=5000, pickable=True))

deck = pdk.Deck(layers=layers, initial_view_state=pdk.ViewState(latitude=-0.5, longitude=11.8, zoom=5.3), map_style="light", tooltip={"text":"{name}"})
st.pydeck_chart(deck, height=500)

if df is None:
    st.warning("Ajoute bien Releves.csv à la racine du repo GitHub à côté de app.py")
    st.stop()

# --- DASHBOARD ---
st.divider()
c1,c2 = st.columns(2)
with c1:
    codes = sorted(df["station"].unique().tolist())
    sel_st = st.selectbox("📍 Station", codes, format_func=lambda x: f"{x} - {STATIONS_NOMS.get(x,x)}")
with c2:
    params = sorted(df["parametre"].dropna().unique().tolist()) if "parametre" in df.columns else ["Niveau d'eau"]
    sel_param = st.selectbox("📈 Paramètre", params)

df_f = df[(df["station"]==sel_st) & (df["parametre"]==sel_param)] if "parametre" in df.columns else df[df["station"]==sel_st]
df_f = df_f.sort_values("datetime")

if not df_f.empty:
    st.metric("Dernière valeur", f"{df_f.iloc[-1]['valeur']} - {df_f.iloc[-1]['date']} {df_f.iloc[-1]['heure']}")
    fig = px.line(df_f, x="datetime", y="valeur", title=f"{sel_param} - {STATIONS_NOMS.get(sel_st, sel_st)}")
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(df_f.tail(30), use_container_width=True)
else:
    st.info("Pas de données pour ce paramètre sur cette station")
