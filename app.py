import streamlit as st
import pandas as pd
import os, re, csv, shutil, unicodedata, tempfile, time
from pathlib import Path
from ftplib import FTP
from collections import defaultdict
from datetime import datetime, timedelta
import geopandas as gpd
import pydeck as pdk
import streamlit.components.v1 as components

try:
    import plotly.express as px
    HAS_PLOTLY = True
except:
    HAS_PLOTLY = False
try:
    from streamlit_autorefresh import st_autorefresh
    HAS_AUTOREFRESH = True
except:
    HAS_AUTOREFRESH = False
try:
    import kaleido
    HAS_KALEIDO = True
except:
    HAS_KALEIDO = False

st.set_page_config(page_title="Hydrométrie du Gabon - DGE", layout="wide")
if HAS_AUTOREFRESH:
    st_autorefresh(interval=3600000, key="hourly_sync")

FTP_HOST = "ftp.sommeupservices.ga"
FTP_PORT = 21
FTP_USER = "2312136aE79X7"
FTP_PASS = "FTP@dgeau20"
FTP_DOSSIERS = ["Donnees_Hydro", "FOUGAMOU"]
BASE_HYDROMET = Path(__file__).parent
DOSSIER_ENTREE = BASE_HYDROMET / "DonneesEntrees"
DOSSIER_SORTIE = BASE_HYDROMET / "DonneesCSV"
DOSSIER_STATION = DOSSIER_SORTIE / "Combine_Station"
RELEVES_FINAL = BASE_HYDROMET / "Releves.csv"

STATIONS = {"1141902405":"Mandilou Aviation","1141900112":"Saint-Martin"}
CAPTEURS = {"0001":"Niveau d'eau","0002":"Pluie","0010":"Température Eau","0020":"Conductivité","0021":"Salinité","0022":"TDS","0030":"Turbidité","0031":"MeS","0040":"Température Air","0041":"Humidité Air","0042":"Pression Atmosphérique","0043":"Vitesse vent","0044":"Direction vent","0045":"Radiation solaire","0100":"Batterie"}
UNITES = {"0001":"cm","0002":"mm","0010":"°C","0020":"µS","0021":"PSU","0022":"PPM","0030":"NTU","0031":"ml/g","0040":"°C","0041":"%","0042":"hPa","0043":"m/s","0044":"°","0045":"w/m²","0100":"V"}

RE_ENTETE = re.compile(r"<STATION>(?P<station>[^<]*)</STATION>\s*<SENSOR>(?P<capteur>[^<]*)</SENSOR>(?:\s*<DATEFORMAT>(?P<dateformat>[^<]*)</DATEFORMAT>)?", re.IGNORECASE)
RE_CODE = re.compile(r"^\[(?P<code>[^\]]*)\]$")
ENTETE_CSV = ["station","nom_station","capteur","parametre","date","heure","valeur","code"]
IDX_DATE, IDX_HEURE, IDX_VALEUR, IDX_CODE = 4,5,6,7
SEPARATEUR_CSV = ";"
FORMAT_DATE_SORTIE = "%d/%m/%Y"
FORMAT_HEURE_SORTIE = "%H:%M:%S"
ENCODAGES = ("utf-8-sig", "cp1252", "latin-1")

def nom_fichier_sur(t): return re.sub(r"\W+", "_", t, flags=re.UNICODE).strip("_")
def lire_texte(c): 
    for enc in ENCODAGES:
        try: return c.read_text(encoding=enc)
        except: continue
    return c.read_text(encoding="utf-8", errors="replace")
def format_python(f): return f.upper().replace("YYYY","%Y").replace("YY","%y").replace("MM","%m").replace("DD","%d")
def formater_date_heure(d,h,fd):
    h=h.strip()
    try: d=datetime.strptime(d, format_python(fd)).strftime(FORMAT_DATE_SORTIE)
    except: pass
    for fmt in ("%H%M%S","%H%M"):
        try: h=datetime.strptime(h, fmt).strftime(FORMAT_HEURE_SORTIE); break
        except: continue
    return d,h
def lire_mis(chemin):
    lignes=[]; station=capteur=""; fmt_date="YYYYMMDD"
    for ligne in lire_texte(chemin).splitlines():
        ligne=ligne.strip()
        if not ligne: continue
        m=RE_ENTETE.search(ligne)
        if m: station=m.group("station").strip(); capteur=m.group("capteur").strip(); fmt_date=(m.group("dateformat") or "YYYYMMDD").strip(); continue
        champs=[c.strip() for c in ligne.split(";")]
        if len(champs)<3: continue
        date,heure,valeur=champs[0],champs[1],";".join(champs[2:])
        code=""; mc=RE_CODE.match(valeur)
        if mc: code,valeur=mc.group("code"),""
        dt,ht=formater_date_heure(date,heure,fmt_date)
        lignes.append([station, STATIONS.get(station,station), capteur, CAPTEURS.get(capteur,capteur), dt, ht, valeur, code])
    return lignes
def cle_tri(l):
    try: d=datetime.strptime(l[IDX_DATE], FORMAT_DATE_SORTIE).strftime("%Y%m%d")
    except: d=l[IDX_DATE]
    try: h=datetime.strptime(l[IDX_HEURE], FORMAT_HEURE_SORTIE).strftime("%H%M%S")
    except: h=l[IDX_HEURE]
    return d+h
def trier_sans_doublons(lignes):
    vues,res=set(),[]
    for ligne in sorted(lignes, key=lambda l:(cle_tri(l),l)):
        sig=tuple(ligne)
        if sig not in vues: vues.add(sig); res.append(ligne)
    return res

# --- SYNC FTP (ta version d'origine simplifiée) ---
def sync_ftp_and_convert(bar, txt):
    DOSSIER_ENTREE.mkdir(parents=True, exist_ok=True)
    try:
        ftp = FTP()
        ftp.connect(FTP_HOST, FTP_PORT, timeout=20)
        ftp.login(FTP_USER, FTP_PASS)
        ftp.set_pasv(True)
        all_files=[]
        for dossier in FTP_DOSSIERS:
            try:
                ftp.cwd(f"/{dossier}")
                all_files += [(dossier, f) for f in ftp.nlst() if f.lower().endswith(".mis")]
            except: continue
        uniques = {Path(f).name: (d,f) for d,f in all_files}
        for i,(d,fname) in enumerate(uniques.values()):
            local = DOSSIER_ENTREE / Path(fname).name
            if not local.exists() or local.stat().st_size < 100:
                txt.text(f"📥 {fname}...")
                bar.progress((i+1)/len(uniques))
                try:
                    ftp.cwd(d)
                    with open(local,'wb') as lf: ftp.retrbinary(f"RETR {fname}", lf.write)
                except: pass
        ftp.quit()
    except Exception as e:
        txt.text(f"FTP offline: {e}")
    return True

st.markdown("""<style>.last-box {background:linear-gradient(135deg,#00b050 0%,#007a33 100%); color:white; border-radius:14px; padding:14px 18px; margin-bottom:12px; display:flex; justify-content:space-between; align-items:center}</style>""", unsafe_allow_html=True)
st.title("Hydrométrie du Gabon : Direction Générale de l'Eau")

bar = st.progress(0)
txt = st.empty()
sync_ftp_and_convert(bar, txt)
bar.empty()
txt.empty()

# --- GIS OPTIMISÉ POUR TES 3 FICHIERS ---
@st.cache_data
def load_gis():
    base=Path(__file__).parent
    data={}
    try:
        if (base/"Limite_Gabon.shp").exists():
            gdf=gpd.read_file(base/"Limite_Gabon.shp", engine="pyogrio")
            if gdf.crs: gdf=gdf.to_crs(4326)
            gdf.columns=[c.lower() for c in gdf.columns]
            data["limite"]=gdf
    except: pass
    try:
        if (base/"Rivieres_Gabon.shp").exists():
            gdf=gpd.read_file(base/"Rivieres_Gabon.shp", engine="pyogrio")
            if gdf.crs: gdf=gdf.to_crs(4326)
            gdf.columns=[c.lower() for c in gdf.columns]
            data["rivieres"]=gdf
    except: pass
    try:
        if (base/"Stations.shp").exists():
            gdf=gpd.read_file(base/"Stations.shp", engine="pyogrio")
            if gdf.crs: gdf=gdf.to_crs(4326)
            gdf.columns=[c.lower() for c in gdf.columns]
            data["stations"]=gdf
    except: pass
    return data

# --- NOUVEAU LOAD RELEVES AVEC FALLBACK MANDILOU ---
@st.cache_data(ttl=600)
def load_releves():
    df_final = None
    # 1. Essaie Releves.csv
    if RELEVES_FINAL.exists():
        try:
            df=pd.read_csv(RELEVES_FINAL, sep=';', encoding='utf-8-sig', errors='ignore')
            df.columns=[c.lower().strip() for c in df.columns]
            df["station"]=df["station"].astype(str).str.strip()
            df["capteur"]=df["capteur"].astype(str).str.strip().str.zfill(4)
            if "date" in df.columns and "heure" in df.columns:
                df["datetime"]=pd.to_datetime(df["date"].astype(str)+" "+df["heure"].astype(str), dayfirst=True, errors='coerce')
            df["valeur"]=pd.to_numeric(df["valeur"].astype(str).str.replace(',','.'), errors='coerce')
            df_final=df
        except: pass
    
    # 2. FALLBACK : scanne les .mis locaux pour compléter / créer df si besoin
    try:
        if DOSSIER_ENTREE.exists():
            tous=[]
            for mis in DOSSIER_ENTREE.glob("*.mis"):
                tous.extend(lire_mis(mis))
            for mis in DOSSIER_ENTREE.glob("*.MIS"):
                tous.extend(lire_mis(mis))
            if tous:
                df_mis = pd.DataFrame(tous, columns=ENTETE_CSV)
                df_mis["station"]=df_mis["station"].astype(str)
                df_mis["capteur"]=df_mis["capteur"].astype(str).str.zfill(4)
                df_mis["datetime"]=pd.to_datetime(df_mis["date"].astype(str)+" "+df_mis["heure"].astype(str), dayfirst=True, errors='coerce')
                df_mis["valeur"]=pd.to_numeric(df_mis["valeur"].astype(str).str.replace(',','.'), errors='coerce')
                if df_final is None or df_final.empty:
                    df_final = df_mis
                else:
                    # Fusionne pour récupérer Mandilou même si pas dans Releves.csv
                    df_final = pd.concat([df_final, df_mis], ignore_index=True).drop_duplicates()
    except Exception as e:
        print(e)

    return df_final

gis_data=load_gis()
df=load_releves()

if df is None or df.empty:
    st.error("Aucune donnée trouvée. Vérifie que DonneesEntrees contient des .mis ou que Releves.csv est présent.")
    st.stop()

# Debug visible pour toi
with st.expander("🔍 Debug - Vérification Mandilou"):
    st.write("Stations dans Releves/données:", df["station"].unique().tolist())
    st.write("Mandilou présent ?", "1141902405" in df["station"].astype(str).values)
    st.write("Nombre de mesures Mandilou:", len(df[df["station"].astype(str)=="1141902405"]))
    st.write("Fichiers .mis locaux:", [p.name for p in DOSSIER_ENTREE.glob("*")] if DOSSIER_ENTREE.exists() else "Dossier vide")

# Suite identique à ton dashboard
station_names={}
if "nom_station" in df.columns:
    for code in df["station"].unique():
        try: station_names[str(code)]=df[df["station"]==code]["nom_station"].dropna().iloc[0]
        except: station_names[str(code)]=str(code)
for k,v in STATIONS.items():
    if k not in station_names: station_names[k]=v

def format_station(code):
    if code=="Toutes les stations": return "🌍 Toutes les stations"
    return f"{code} - {station_names.get(str(code), code)}"

col_st, col_par, col_periode = st.columns(3)
with col_st:
    codes_csv=sorted(df["station"].dropna().astype(str).unique().tolist())
    # FORCE l'ajout de Mandilou dans la liste même si pas de data
    for c in STATIONS.keys():
        if c not in codes_csv: codes_csv.append(c)
    sel_station=st.selectbox("📍 Choisir station", ["Toutes les stations"]+sorted(codes_csv), format_func=format_station)
with col_par:
    params=sorted(df["parametre"].dropna().unique().tolist()) if "parametre" in df.columns else ["Niveau d'eau"]
    default_idx=next((i for i,p in enumerate(params) if "niveau" in p.lower()),0)
    sel_param=st.selectbox("📈 Paramètre", params, index=default_idx)
with col_periode:
    sel_periode=st.selectbox("🗓️ Période", ["Toutes", "Semaine", "Mois", "Année"], index=0)

df_f=df[df["parametre"]==sel_param].copy() if "parametre" in df.columns else df.copy()
if sel_station!="Toutes les stations": df_f=df_f[df_f["station"].astype(str)==str(sel_station)]

if not df_f.empty and "datetime" in df_f.columns:
    now = df_f["datetime"].max()
    if pd.notna(now):
        if sel_periode=="Semaine": df_f = df_f[df_f["datetime"] >= now - timedelta(days=7)]
        elif sel_periode=="Mois": df_f = df_f[df_f["datetime"] >= now - timedelta(days=30)]
        elif sel_periode=="Année": df_f = df_f[df_f["datetime"] >= now - timedelta(days=365)]

# Affichage carte + graph (ton code d'origine)
col_gauche, col_droite = st.columns([1.1,1.5], gap="large")
with col_gauche:
    st.subheader(f"🗺️ {format_station(sel_station)}")
    layers=[]
    if "limite" in gis_data:
        for geom in gis_data["limite"].geometry:
            try:
                if geom.geom_type=="Polygon": layers.append(pdk.Layer("PolygonLayer", data=[{"polygon":[list(geom.exterior.coords)]}], get_polygon="polygon[0]", get_fill_color=[0,0,0,6], get_line_color=[0,0,0,180], line_width_min_pixels=2))
                elif geom.geom_type=="MultiPolygon":
                    for g in geom.geoms: layers.append(pdk.Layer("PolygonLayer", data=[{"polygon":[list(g.exterior.coords)]}], get_polygon="polygon[0]", get_fill_color=[0,0,0,6], get_line_color=[0,0,0,180], line_width_min_pixels=2)); break
            except: pass
    if "rivieres" in gis_data:
        lines=[]
        for geom in gis_data["rivieres"].geometry:
            try:
                if geom.geom_type=="LineString": lines.append({"path":list(geom.coords)})
                elif geom.geom_type=="MultiLineString":
                    for g in geom.geoms: lines.append({"path":list(g.coords)})
            except: continue
        if lines: layers.append(pdk.Layer("PathLayer", data=lines, get_path="path", get_color=[0,110,255,120], width_min_pixels=2))
    if "stations" in gis_data:
        gdf_st = gis_data["stations"]
        pts=[]
        code_col = next((c for c in gdf_st.columns if "code" in c or "station" in c or "id" in c or "point" in c), gdf_st.columns[0])
        for _, row in gdf_st.iterrows():
            try:
                lat = row.geometry.y if row.geometry.geom_type=="Point" else row.geometry.centroid.y
                lon = row.geometry.x if row.geometry.geom_type=="Point" else row.geometry.centroid.x
                pts.append({"lat":lat,"lon":lon,"full":str(row[code_col])})
            except: pass
        if pts: layers.append(pdk.Layer("ScatterplotLayer", data=pts, get_position='[lon, lat]', get_color='[255, 0, 0, 200]', get_radius=4000, radius_min_pixels=5, pickable=True))
    deck = pdk.Deck(layers=layers, initial_view_state=pdk.ViewState(latitude=-0.5, longitude=11.8, zoom=5.2), map_style="light", tooltip={"text": "{full}"})
    st.pydeck_chart(deck, height=500)

with col_droite:
    st.subheader(f"📊 {sel_param}")
    if not df_f.empty:
        st.metric("Mesures", len(df_f))
        if HAS_PLOTLY:
            fig=px.line(df_f.sort_values("datetime"), x="datetime", y="valeur", title=f"{sel_param} - {sel_station}")
            st.plotly_chart(fig, use_container_width=True)

st.divider()
if not df_f.empty:
    st.dataframe(df_f.sort_values("datetime", ascending=False).head(30), use_container_width=True)
