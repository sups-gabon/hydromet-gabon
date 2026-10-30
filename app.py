import streamlit as st
import pandas as pd
from pathlib import Path
import geopandas as gpd
import pydeck as pdk

st.set_page_config(page_title="Hydrométrie du Gabon - DGE", layout="wide")
st.title("Hydrométrie du Gabon : Direction Générale de l'Eau")

BASE = Path(__file__).parent

@st.cache_data
def load_gis():
    data = {}
    try:
        if (BASE / "Limite_Gabon.shp").exists():
            gdf = gpd.read_file(BASE / "Limite_Gabon.shp", engine="pyogrio")
            if gdf.crs: gdf = gdf.to_crs(4326)
            data["limite"] = gdf
    except Exception as e:
        st.write(f"Limite error: {e}")
    try:
        if (BASE / "Rivieres_Gabon.shp").exists():
            gdf = gpd.read_file(BASE / "Rivieres_Gabon.shp", engine="pyogrio")
            if gdf.crs: gdf = gdf.to_crs(4326)
            data["rivieres"] = gdf
    except Exception as e:
        st.write(f"Rivieres error: {e}")
    try:
        if (BASE / "Stations.shp").exists():
            gdf = gpd.read_file(BASE / "Stations.shp", engine="pyogrio")
            if gdf.crs: gdf = gdf.to_crs(4326)
            data["stations"] = gdf
    except Exception as e:
        st.write(f"Stations error: {e}")
    return data

gis = load_gis()

layers = []
if "limite" in gis:
    for geom in gis["limite"].geometry:
        if geom and not geom.is_empty and geom.geom_type == "Polygon":
            layers.append(pdk.Layer("PolygonLayer", data=[{"polygon": [list(geom.exterior.coords)]}], get_polygon="polygon[0]", get_fill_color=[0,0,0,0], get_line_color=[0,100,0,200], line_width_min_pixels=2))

if "rivieres" in gis:
    lines = []
    for geom in gis["rivieres"].geometry:
        if geom and not geom.is_empty:
            if geom.geom_type == "LineString":
                lines.append({"path": list(geom.coords)})
    if lines:
        layers.append(pdk.Layer("PathLayer", data=lines, get_path="path", get_color=[0,120,255,180], width_min_pixels=2))

if "stations" in gis:
    pts = []
    for _, row in gis["stations"].iterrows():
        try:
            pts.append({"lat": row.geometry.y, "lon": row.geometry.x, "name": str(row.iloc[0])})
        except: pass
    if pts:
        layers.append(pdk.Layer("ScatterplotLayer", data=pts, get_position='[lon, lat]', get_color='[255,0,0,200]', get_radius=4000, pickable=True))

view = pdk.ViewState(latitude=-0.5, longitude=11.8, zoom=5.2)
deck = pdk.Deck(layers=layers, initial_view_state=view, map_style="light", tooltip={"text": "{name}"})
st.pydeck_chart(deck, height=600)

st.success("Carte chargée - Limite_Gabon / Rivieres_Gabon / Stations")

# Partie données - ne bloque plus l'app
RELEVES = BASE / "Releves.csv"
if RELEVES.exists():
    try:
        df = pd.read_csv(RELEVES, sep=';', encoding='utf-8-sig', errors='ignore')
        st.dataframe(df.head(50), use_container_width=True)
        if "1141902405" in df.astype(str).values:
            st.success("Mandilou Aviation détecté dans Releves.csv")
    except Exception as e:
        st.warning(f"Releves.csv illisible: {e}")
else:
    st.info("Releves.csv absent - ajoute-le à GitHub pour voir Mandilou Aviation. La carte fonctionne déjà.")
