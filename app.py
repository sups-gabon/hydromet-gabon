import streamlit as st
import pandas as pd
import geopandas as gpd
import pydeck as pdk

st.set_page_config(page_title="Hydromet Gabon", layout="wide", page_icon="💧")
st.title("💧 Tableau de bord Hydromet - Gabon")
st.markdown("Visualisation des stations, cours d'eau et limites - [sommeupservices.ga](https://hydromet.sommeupservices.ga)")

# --- 1. CHARGEMENT DES SHAPEFILES ---
@st.cache_data
def load_shapefiles():
    data = {}
    try:
        data['limite'] = gpd.read_file("Limite_Gabon.shp").to_crs(epsg=4326)
    except Exception as e:
        st.warning(f"Limite_Gabon.shp non trouvé: {e}")
        data['limite'] = None
    try:
        data['rivieres'] = gpd.read_file("Rivieres_Gabon.shp").to_crs(epsg=4326)
    except Exception as e:
        data['rivieres'] = None
    try:
        data['stations'] = gpd.read_file("Stations.shp").to_crs(epsg=4326)
    except Exception as e:
        data['stations'] = None
    return data

shp = load_shapefiles()

# --- 2. DONNÉES GOOGLE SHEET (à remplacer par ton URL si tu veux) ---
# Laisse vide si tu n'utilises que les shapefiles
SHEET_URL = "" # ex: https://docs.google.com/spreadsheets/d/.../export?format=csv

@st.cache_data(ttl=300)
def load_releves():
    if SHEET_URL:
        try:
            return pd.read_csv(SHEET_URL)
        except:
            return None
    return None

df_releves = load_releves()

# --- 3. CARTE ---
st.subheader("🗺️ Carte du Gabon")

layers = []

if shp['limite'] is not None:
    layers.append(pdk.Layer(
        "GeoJsonLayer",
        shp['limite'],
        get_fill_color=[0,0,0,0],
        get_line_color=[0, 100, 0, 200],
        line_width_min_pixels=2,
    ))

if shp['rivieres'] is not None:
    # Pour les lignes
    layers.append(pdk.Layer(
        "GeoJsonLayer",
        shp['rivieres'],
        get_line_color=[0, 120, 255, 180],
        line_width_min_pixels=1.5,
    ))

if shp['stations'] is not None:
    # On récupère lat/lon depuis le shapefile
    shp['stations']['lon'] = shp['stations'].geometry.x
    shp['stations']['lat'] = shp['stations'].geometry.y
    layers.append(pdk.Layer(
        "ScatterplotLayer",
        shp['stations'],
        get_position='[lon, lat]',
        get_color='[255, 0, 0, 200]',
        get_radius=3000,
        pickable=True,
    ))
    st.caption(f"{len(shp['stations'])} stations chargées")

view_state = pdk.ViewState(latitude=0.0, longitude=11.8, zoom=5.5, pitch=0)

tooltip = {"html": "<b>Station:</b> {Nom} <br/> <b>Rivière:</b> {Riviere}", "style": {"color": "white"}}

st.pydeck_chart(pdk.Deck(layers=layers, initial_view_state=view_state, tooltip=tooltip, map_style="mapbox://styles/mapbox/light-v10"))

# --- 4. TABLEAUX ---
c1, c2 = st.columns(2)
with c1:
    if shp['stations'] is not None:
        st.dataframe(shp['stations'].drop(columns='geometry'), use_container_width=True)
with c2:
    if df_releves is not None:
        st.dataframe(df_releves, use_container_width=True)
    else:
        st.info("Ajoute ton URL Google Sheet dans SHEET_URL pour afficher les relevés.")

st.success("App opérationnelle - shapefiles intégrés")
