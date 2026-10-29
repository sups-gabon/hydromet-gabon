import streamlit as st
import geopandas as gpd
import pandas as pd
import matplotlib.pyplot as plt

st.set_page_config(page_title="Hydromet Gabon", layout="wide")
st.title("Tableau de bord Hydrométrique - Gabon")

@st.cache_data
def load_data():
    limite = gpd.read_file("Limite_Gabon.shp").to_crs(epsg=4326)
    rivieres = gpd.read_file("Rivieres_Gabon.shp").to_crs(epsg=4326)
    stations = gpd.read_file("Stations.shp").to_crs(epsg=4326)
    return limite, rivieres, stations

try:
    limite, rivieres, stations = load_data()
except Exception as e:
    st.error(f"Erreur chargement shapefiles: {e}")
    st.stop()

# --- CARTE comme avant ---
fig, ax = plt.subplots(figsize=(10, 8))
limite.boundary.plot(ax=ax, color="darkgreen", linewidth=1.2)
rivieres.plot(ax=ax, color="#1E90FF", linewidth=1.5)
stations.plot(ax=ax, color="red", markersize=15)

ax.set_axis_off()
ax.set_title("")
st.pyplot(fig)

# --- TABLEAU comme sur ta capture ---
st.subheader("Stations")
# On affiche exactement les colonnes de ta capture
cols_to_show = [c for c in ["Point","Province","Lieudit","DR__m_","Pente____","Altitude__","Long","Xlong"] if c in stations.columns]

if cols_to_show:
    st.dataframe(stations[cols_to_show].drop(columns='geometry', errors='ignore'), use_container_width=True, height=300)
else:
    # fallback : affiche tout sans géométrie
    st.dataframe(stations.drop(columns='geometry', errors='ignore'), use_container_width=True)

st.success("Application opérationnelle - shapefiles intégrés")
