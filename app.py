import streamlit as st
import sys, subprocess, time

def ensure_pkg(pkg, import_name=None):
    import_name = import_name or pkg
    try:
        __import__(import_name)
        return True
    except ImportError:
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet", pkg])
            return True
        except:
            return False

ensure_pkg("kaleido")
ensure_pkg("streamlit-autorefresh", "streamlit_autorefresh")

import pandas as pd
import os, glob, re, csv, shutil, unicodedata, tempfile, socket
from pathlib import Path
from ftplib import FTP, error_temp
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

# AUTO REFRESH TOUTES LES HEURES (3600000 ms = 1h)
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
RELEVES_ONEDRIVE = Path(r"C:\Users\info\OneDrive\Bureau\HYDROMET\Releves.csv")

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
def ecrire_csv(d, lignes):
    d.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(suffix=".csv", dir=str(d.parent))
    os.close(fd)
    try:
        with open(tmp_path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=SEPARATEUR_CSV)
            w.writerow(ENTETE_CSV)
            w.writerows(lignes)
        for _ in range(5):
            try:
                if d.exists(): d.unlink()
                shutil.move(tmp_path, d)
                return
            except PermissionError:
                time.sleep(1)
    finally:
        if os.path.exists(tmp_path):
            try: os.unlink(tmp_path)
            except: pass
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
def lire_csv(c):
    with open(c, newline="", encoding="utf-8-sig") as f: ll=list(csv.reader(f, delimiter=SEPARATEUR_CSV)); return (ll[0] if ll else []), (ll[1:] if ll else [])
def mettre_a_jour_csv(dest, nouvelles, exclure_erreurs=False):
    if exclure_erreurs: nouvelles=[l for l in nouvelles if not est_erreur(l)]
    nouvelles=trier_sans_doublons(nouvelles)
    if not dest.exists():
        if not nouvelles: return "IGNORÉ"
        ecrire_csv(dest,nouvelles); return f"CRÉÉ {len(nouvelles)}"
    entete,existantes=lire_csv(dest)
    if entete!=ENTETE_CSV: ecrire_csv(dest,nouvelles); return "REMPLACÉ"
    if existantes==nouvelles: return "INCHANGÉ"
    fusion=trier_sans_doublons([l for l in existantes+nouvelles if not (exclure_erreurs and est_erreur(l))])
    if fusion==existantes: return "À JOUR"
    if not fusion: dest.unlink(); return "SUPPRIMÉ"
    ecrire_csv(dest,fusion); return f"FUSIONNÉ +{len(fusion)-len(existantes)}"
def est_erreur(l): return l[IDX_CODE].strip()!="" and l[IDX_VALEUR].strip()==""

def get_last_datetime_from_releves():
    try:
        if not RELEVES_FINAL.exists(): return None
        df = pd.read_csv(RELEVES_FINAL, sep=';', encoding='utf-8-sig', encoding_errors='ignore')
        df.columns = [c.lower().strip() for c in df.columns]
        if "date" not in df.columns or "heure" not in df.columns: return None
        df["dt"] = pd.to_datetime(df["date"].astype(str)+" "+df["heure"].astype(str), dayfirst=True, errors='coerce')
        return df["dt"].max()
    except:
        return None

def sync_ftp_and_convert(progress_bar, status_text):
    DOSSIER_ENTREE.mkdir(parents=True, exist_ok=True)
    DOSSIER_SORTIE.mkdir(parents=True, exist_ok=True)
    last_dt = get_last_datetime_from_releves()
    if last_dt and pd.notna(last_dt):
        diff_min = (datetime.now() - last_dt.to_pydatetime().replace(tzinfo=None)).total_seconds() / 60
        if diff_min < 60:
            status_text.text(f"✅ Données à jour ({last_dt.strftime('%d/%m/%Y %H:%M')} il y a {int(diff_min)} min)")
            progress_bar.progress(1.0)
            time.sleep(0.5)
            _, existantes = lire_csv(RELEVES_FINAL)
            return len(existantes), 0, 0
    def get_ftp():
        ftp = FTP()
        ftp.connect(FTP_HOST, FTP_PORT, timeout=30)
        ftp.login(FTP_USER, FTP_PASS)
        ftp.set_pasv(True)
        return ftp
    status_text.text(f"🔄 Sync FTP {FTP_HOST}...")
    ftp = get_ftp()
    all_mis_files = []
    for dossier in FTP_DOSSIERS:
        try:
            ftp.cwd(f"/{dossier}")
            fichiers = [f for f in ftp.nlst() if f.lower().endswith(".mis")]
            for f in fichiers: all_mis_files.append((f"/{dossier}", f))
        except:
            try:
                ftp.cwd(dossier)
                fichiers = [f for f in ftp.nlst() if f.lower().endswith(".mis")]
                for f in fichiers: all_mis_files.append((dossier, f))
            except: continue
    uniques = {}
    for dossier, fname in all_mis_files: uniques[Path(fname).name] = (dossier, fname)
    all_mis_files = list(uniques.values())
    fichiers_a_telecharger = []
    for dossier_ftp, fname in all_mis_files:
        local_path = DOSSIER_ENTREE / Path(fname).name
        if not local_path.exists() or local_path.stat().st_size < 100:
            fichiers_a_telecharger.append((dossier_ftp, fname))
    if fichiers_a_telecharger:
        status_text.text(f"📥 {len(fichiers_a_telecharger)} nouveaux fichiers...")
    for i, (dossier_ftp, fname) in enumerate(fichiers_a_telecharger):
        progress_bar.progress((i+1)/len(fichiers_a_telecharger)*0.7 if fichiers_a_telecharger else 0.7)
        local_path = DOSSIER_ENTREE / Path(fname).name
        try:
            ftp.cwd(dossier_ftp)
            with open(local_path, 'wb') as lf: ftp.retrbinary(f"RETR {fname}", lf.write, blocksize=32768)
        except:
            try: 
                ftp = get_ftp()
                ftp.cwd(dossier_ftp)
                with open(local_path, 'wb') as lf: ftp.retrbinary(f"RETR {fname}", lf.write, blocksize=32768)
            except: continue
    try: ftp.quit()
    except: pass
    if fichiers_a_telecharger:
        nouveaux_mis = [DOSSIER_ENTREE / Path(f[1]).name for f in fichiers_a_telecharger]
    else:
        nouveaux_mis = [] if RELEVES_FINAL.exists() else sorted(p for p in DOSSIER_ENTREE.iterdir() if p.is_file() and p.suffix.lower()==".mis")
    tous_nouveaux = []
    par = defaultdict(list)
    for src in nouveaux_mis:
        try:
            mesures = lire_mis(src)
            dest = DOSSIER_SORTIE/(src.stem+".csv")
            mettre_a_jour_csv(dest, mesures)
            tous_nouveaux.extend(mesures)
            for l in mesures: par[(l[0],l[2])].append(l)
        except: pass
    for (station, capteur), mesures in par.items():
        dossier = DOSSIER_STATION/f"{station}_{nom_fichier_sur(STATIONS.get(station,station))}"
        nom = f"{capteur}_{nom_fichier_sur(CAPTEURS.get(capteur,capteur))}.csv"
        mettre_a_jour_csv(dossier/nom, mesures, exclure_erreurs=True)
    progress_bar.progress(0.9)
    if RELEVES_FINAL.exists() and tous_nouveaux:
        _, existantes = lire_csv(RELEVES_FINAL)
        fusion = trier_sans_doublons(existantes + tous_nouveaux)
        ecrire_csv(RELEVES_FINAL, fusion)
        return len(fusion), len(all_mis_files), len(fichiers_a_telecharger)
    elif RELEVES_FINAL.exists():
        _, existantes = lire_csv(RELEVES_FINAL)
        return len(existantes), len(all_mis_files), 0
    else:
        tous_nouveaux = trier_sans_doublons(tous_nouveaux)
        ecrire_csv(RELEVES_FINAL, tous_nouveaux)
        return len(tous_nouveaux), len(all_mis_files), len(fichiers_a_telecharger)

st.markdown("""
<style>
.last-box {background:linear-gradient(135deg,#00b050 0%,#007a33 100%); color:white; border-radius:14px; padding:14px 18px; margin-bottom:12px; display:flex; justify-content:space-between; align-items:center}
.last-box .left h4{margin:0; font-size:14px; opacity:0.9}
.last-box .left h2{margin:4px 0; font-size:28px}
.last-box .left p{margin:0; font-size:13px; opacity:0.9}
.last-box .arrow {font-size:48px; font-weight:bold; line-height:1; margin-left:15px}
.arrow-up {color:#aaffaa}
.arrow-down {color:#ffaaaa}
.arrow-stable {color:#ffffff}
@media print { header, footer, [data-testid="stSidebar"], .stButton, [data-testid="stDownloadButton"] { display:none !important; } }
</style>
""", unsafe_allow_html=True)

st.title("Hydrométrie du Gabon : Direction Générale de l'Eau")

# ===== SYNC AUTOMATIQUE AU LANCEMENT =====
if "last_sync_time" not in st.session_state:
    st.session_state.last_sync_time = None

bar = st.progress(0)
txt = st.empty()
try:
    res = sync_ftp_and_convert(bar, txt)
    nb_lignes, nb_fichiers, nb_new = res
    bar.empty()
    if nb_new == 0 and nb_fichiers == 0:
        txt.info(f"✅ Auto-sync : Données à jour - {nb_lignes} mesures (re-vérif auto dans 1h)")
    elif nb_new == 0:
        txt.success(f"✅ Auto-sync : {nb_fichiers} fichiers vérifiés, {nb_lignes} mesures - Prochaine sync dans 1h")
    else:
        txt.success(f"✅ Auto-sync : {nb_new} nouveaux / {nb_fichiers} au total -> {nb_lignes} mesures")
    st.session_state.last_sync_time = datetime.now()
    time.sleep(2)
    txt.empty()
except Exception as e:
    bar.empty()
    txt.warning(f"Sync auto échouée (mode hors-ligne) : {e}")

# Affichage info dernière sync
if st.session_state.last_sync_time:
    st.caption(f"🔄 Dernière synchronisation auto : {st.session_state.last_sync_time.strftime('%d/%m/%Y %H:%M:%S')} | Prochaine dans 1h")

def normalize_code(s):
    s=str(s).lower().strip()
    s=''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c)!='Mn')
    return s.replace(" ","").replace("-","").replace("_","")

@st.cache_data
def load_gis():
    data={}; base=Path(__file__).parent
    for path in glob.glob(os.path.join(base, "**", "*.shp"), recursive=True):
        low=os.path.basename(path).lower()
        try:
            gdf=gpd.read_file(path)
            if gdf.empty: continue
            if gdf.crs: gdf=gdf.to_crs(epsg=4326)
            gdf.columns=[c.lower() for c in gdf.columns]
            if "limite" in low: data["limite"]=gdf
            elif "riv" in low: data["rivieres"]=gdf
            elif "station" in low: data["stations"]=gdf
        except: pass
    return data

@st.cache_data
def load_releves():
    candidates=[RELEVES_FINAL, RELEVES_ONEDRIVE, Path(__file__).parent/"Releves.csv"]
    for p in candidates:
        if p.exists():
            try:
                df=pd.read_csv(p, sep=';', encoding='utf-8-sig', encoding_errors='ignore')
                if "valeur" not in [c.lower() for c in df.columns]:
                    df=pd.read_csv(p, sep=None, engine='python', encoding='utf-8-sig', encoding_errors='ignore')
                df.columns=[c.lower().strip() for c in df.columns]
                if "valeur" not in df.columns: continue
                df["station"]=df["station"].astype(str).str.strip()
                df["capteur"]=df["capteur"].astype(str).str.strip().str.zfill(4)
                if "date" in df.columns and "heure" in df.columns:
                    df["datetime"]=pd.to_datetime(df["date"].astype(str)+" "+df["heure"].astype(str), dayfirst=True, errors='coerce')
                df["valeur"]=pd.to_numeric(df["valeur"].astype(str).str.replace(',','.'), errors='coerce')
                if df["valeur"].notna().sum()>0: return df
            except: continue
    return None

gis_data=load_gis()
df=load_releves()
if df is None:
    st.warning("Aucun Releves.csv trouvé."); st.stop()

station_names={}
if "nom_station" in df.columns:
    for code in df["station"].unique():
        try: station_names[code]=df[df["station"]==code]["nom_station"].dropna().iloc[0]
        except: station_names[code]=code

def format_station(code):
    if code=="Toutes les stations": return "🌍 Toutes les stations"
    nom=station_names.get(code,"")
    return f"{code} - {nom}" if nom and nom!=code else code

col_st, col_par, col_periode = st.columns(3)
with col_st:
    codes_csv=sorted(df["station"].dropna().unique().tolist())
    sel_station=st.selectbox("📍 Choisir station", ["Toutes les stations"]+codes_csv, format_func=format_station)
with col_par:
    params=sorted(df["parametre"].dropna().unique().tolist()) if "parametre" in df.columns else ["Niveau d'eau"]
    default_idx=next((i for i,p in enumerate(params) if "niveau" in p.lower()),0)
    sel_param=st.selectbox("📈 Paramètre", params, index=default_idx)
with col_periode:
    sel_periode=st.selectbox("🗓️ Période", ["Toutes", "Semaine", "Mois", "Année"], index=0)

df_f=df[df["parametre"]==sel_param].copy() if "parametre" in df.columns else df.copy()
if sel_station!="Toutes les stations": df_f=df_f[df_f["station"]==sel_station]

code_capteur_actuel = ""
if not df_f.empty and "capteur" in df_f.columns:
    try: code_capteur_actuel = df_f["capteur"].iloc[0]
    except: pass
UNITE_ACTUELLE = UNITES.get(code_capteur_actuel, "")
EST_PLUIE = (code_capteur_actuel == "0002") or ("pluie" in sel_param.lower())

if not df_f.empty and "datetime" in df_f.columns:
    now = df_f["datetime"].max()
    if pd.notna(now):
        if sel_periode=="Semaine": df_f = df_f[df_f["datetime"] >= now - timedelta(days=7)]
        elif sel_periode=="Mois": df_f = df_f[df_f["datetime"] >= now - timedelta(days=30)]
        elif sel_periode=="Année": df_f = df_f[df_f["datetime"] >= now - timedelta(days=365)]

derniere_val = None; date_str = ""; arrow_html = ""
if not df_f.empty and "datetime" in df_f.columns:
    df_sorted = df_f.sort_values("datetime", ascending=False).reset_index(drop=True)
    if len(df_sorted) >= 1:
        derniere = df_sorted.iloc[0]
        derniere_val = derniere["valeur"]
        derniere_date = derniere["datetime"]
        date_str = derniere_date.strftime("%d/%m/%Y %H:%M") if pd.notna(derniere_date) else f"{derniere.get('date','')} {derniere.get('heure','')}"
        if len(df_sorted) >= 2:
            prev_val = df_sorted.iloc[1]["valeur"]
            if pd.notna(derniere_val) and pd.notna(prev_val):
                diff = derniere_val - prev_val
                if diff > 0.001: arrow_html = f'<div class="arrow arrow-up">↗ {diff:+.2f}</div>'
                elif diff < -0.001: arrow_html = f'<div class="arrow arrow-down">↘ {diff:+.2f}</div>'
                else: arrow_html = f'<div class="arrow arrow-stable">→ Stable</div>'

col_gauche, col_droite = st.columns([1.1,1.5], gap="large")
with col_gauche:
    st.subheader(f"🗺️ {format_station(sel_station)}")
    all_pts=[]; selected_point=None
    if "stations" in gis_data:
        gdf_st = gis_data["stations"].copy()
        code_col = next((c for c in gdf_st.columns if "code" in c or "station" in c or "id" in c), gdf_st.columns[0])
        gdf_st["code_original"] = gdf_st[code_col].astype(str).str.strip()
        gdf_st["code_norm"] = gdf_st["code_original"].apply(normalize_code)
        for _, row in gdf_st.iterrows():
            if row.geometry is None or row.geometry.is_empty: continue
            try:
                if row.geometry.geom_type == "Point": lat, lon = row.geometry.y, row.geometry.x
                else: lat, lon = row.geometry.centroid.y, row.geometry.centroid.x
                code = row["code_original"]; nom = station_names.get(code, code)
                all_pts.append({"lat": lat, "lon": lon, "code": code, "code_norm": row["code_norm"], "full": f"{code} - {nom}"})
            except: continue
    if sel_station != "Toutes les stations":
        sel_norm = normalize_code(sel_station)
        for pt in all_pts:
            if pt["code_norm"] == sel_norm or sel_norm in pt["code_norm"] or pt["code_norm"] in sel_norm:
                selected_point = pt; break
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
    autres_pts = [p for p in all_pts if not selected_point or p["code_norm"] != selected_point["code_norm"]]
    if autres_pts:
        layers.append(pdk.Layer("ScatterplotLayer", data=autres_pts, get_position='[lon, lat]', get_color='[255, 0, 0, 200]', get_radius=4000, radius_min_pixels=5, pickable=True))
    if selected_point:
        layers.append(pdk.Layer("ScatterplotLayer", data=[selected_point], get_position='[lon, lat]', get_color='[0, 255, 100, 80]', get_radius=20000, radius_min_pixels=20))
        layers.append(pdk.Layer("ScatterplotLayer", data=[selected_point], get_position='[lon, lat]', get_color='[0, 176, 80, 255]', get_radius=8000, radius_min_pixels=10))
        view_lat, view_lon = selected_point["lat"], selected_point["lon"]; view_zoom = 6.0
    else:
        view_lat, view_lon, view_zoom = -0.5, 11.8, 5.2
    deck = pdk.Deck(layers=layers, initial_view_state=pdk.ViewState(latitude=view_lat, longitude=view_lon, zoom=view_zoom), map_style="light", tooltip={"text": "{full}"})
    st.pydeck_chart(deck, height=500)
    components.html("""
    <div style="text-align:center; margin-top:10px;">
      <button id="dl-map" style="background:#00b050; color:white; border:none; padding:10px 18px; border-radius:8px; font-weight:bold; cursor:pointer; width:100%;">📥 Télécharger Carte en PNG</button>
    </div>
    <script src="https://html2canvas.hertzen.com/dist/html2canvas.min.js"></script>
    <script>
    document.getElementById('dl-map').onclick = function(){
        const mapEl = window.parent.document.querySelector('[data-testid="stDeckGlJsonChart"]');
        if(!mapEl){ alert('Carte non trouvée'); return; }
        html2canvas(mapEl, {scale:2, useCORS:true}).then(canvas=>{
            const link = document.createElement('a');
            link.download = 'carte_gabon.png';
            link.href = canvas.toDataURL();
            link.click();
        });
    }
    </script>
    """, height=70)

with col_droite:
    st.subheader(f"📊 {sel_param} ({UNITE_ACTUELLE}) - {sel_periode}")
    if derniere_val is not None:
        st.markdown(f"""
        <div class="last-box">
            <div class="left">
                <h4>Dernière valeur lue - {format_station(sel_station)}</h4>
                <h2>{derniere_val:.2f} {UNITE_ACTUELLE}</h2>
                <p>📅 {date_str} | {sel_param} | Code {code_capteur_actuel}</p>
            </div>
            {arrow_html}
        </div>
        """, unsafe_allow_html=True)
        if not df_f.empty:
            vmin = df_f["valeur"].min()
            vmax = df_f["valeur"].max()
            vmoy = df_f["valeur"].mean()
            if EST_PLUIE:
                total_pluie = df_f["valeur"].sum()
                k1,k2,k3,k4 = st.columns(4)
                with k1: st.metric("📉 Min", f"{vmin:.2f} {UNITE_ACTUELLE}")
                with k2: st.metric("📈 Max", f"{vmax:.2f} {UNITE_ACTUELLE}")
                with k3: st.metric("⚖️ Moyenne", f"{vmoy:.2f} {UNITE_ACTUELLE}")
                with k4: st.metric("🌧️ Total", f"{total_pluie:.2f} {UNITE_ACTUELLE}")
            else:
                k1,k2,k3 = st.columns(3)
                with k1: st.metric("📉 Min", f"{vmin:.2f} {UNITE_ACTUELLE}")
                with k2: st.metric("📈 Max", f"{vmax:.2f} {UNITE_ACTUELLE}")
                with k3: st.metric("⚖️ Moyenne", f"{vmoy:.2f} {UNITE_ACTUELLE}")
        if HAS_PLOTLY and not df_f.empty:
            fig=px.line(df_f.sort_values("datetime"), x="datetime", y="valeur", title=f"Évolution {sel_param} - {format_station(sel_station)} - {sel_periode}")
            fig.update_layout(height=320, margin=dict(l=10,r=10,t=40,b=10))
            fig.update_traces(line=dict(width=2.2, color="#00b050"))
            fig.update_yaxes(title=f"{sel_param} ({UNITE_ACTUELLE})")
            st.plotly_chart(fig, use_container_width=True)
            if HAS_KALEIDO:
                try:
                    img_bytes = fig.to_image(format="png", scale=2)
                    st.download_button("📥 Télécharger Graphique en PNG", data=img_bytes, file_name=f"graph_{sel_station}_{code_capteur_actuel}_{sel_periode}.png", mime="image/png", use_container_width=True, type="primary")
                except: pass

st.divider()
st.subheader("📋 Dernières valeurs lues")
if not df_f.empty and "datetime" in df_f.columns:
    df_last=df_f.sort_values("datetime", ascending=False).head(30)
    st.dataframe(df_last, use_container_width=True, height=350)

components.html("""
<div style="position:fixed; bottom:20px; right:20px; z-index:99999; background:white; border-radius:12px; box-shadow:0 4px 20px rgba(0,0,0,0.3); padding:12px; border:1px solid #ddd;">
  <button onclick="window.parent.print()" style="background:#ff0000; color:white; border:none; padding:10px 18px; border-radius:8px; font-weight:bold; cursor:pointer; font-size:14px;">🖨️ Exporter Tableau de Bord en PDF</button>
</div>
""", height=80)