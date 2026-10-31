import streamlit as st
import sys, subprocess

def ensure_pkg(pkg, import_name=None):
    try:
        __import__(import_name or pkg)
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet", pkg])

ensure_pkg("kaleido")
ensure_pkg("streamlit-autorefresh", "streamlit_autorefresh")
ensure_pkg("pyogrio")

import pandas as pd
import os, re, csv, shutil, tempfile, time
from pathlib import Path
from ftplib import FTP
from datetime import datetime, timedelta
import geopandas as gpd
import pydeck as pdk
import plotly.express as px
import streamlit.components.v1 as components

try:
    from streamlit_autorefresh import st_autorefresh
    HAS_AUTO = True
except:
    HAS_AUTO = False

st.set_page_config(page_title="Hydrométrie du Gabon - DGE", layout="wide")
if HAS_AUTO:
    st_autorefresh(interval=3600000, key="hourly_sync")

FTP_HOST = st.secrets.get("FTP_HOST", "ftp.sommeupservices.ga")
FTP_PORT = int(st.secrets.get("FTP_PORT", 21))
FTP_USER = st.secrets.get("FTP_USER", "2312136aE79X7")
FTP_PASS = st.secrets.get("FTP_PASS", "FTP@dgeau20")
FTP_DOSSIERS = ["Donnees_Hydro", "FOUGAMOU"]

BASE = Path(__file__).parent
DOSSIER_ENTREE = BASE / "DonneesEntrees"
DOSSIER_SORTIE = BASE / "DonneesCSV"
RELEVES_FINAL = BASE / "Releves.csv"

STATIONS_NOMS = {"1141902405":"Mandilou Aviation","1141900112":"Saint-Martin"}
CAPTEURS = {"0001":"Niveau d'eau","0002":"Pluie","0010":"Température Eau","0020":"Conductivité","0021":"Salinité","0022":"TDS","0030":"Turbidité","0031":"MeS","0040":"Température Air","0041":"Humidité Air","0042":"Pression Atmosphérique","0043":"Vitesse vent","0044":"Direction vent","0045":"Radiation solaire","0100":"Batterie"}
UNITES = {"0001":"cm","0002":"mm","0010":"°C","0020":"µS","0021":"PSU","0022":"PPM","0030":"NTU","0031":"ml/g","0040":"°C","0041":"%","0042":"hPa","0043":"m/s","0044":"°","0045":"w/m²","0100":"V"}

RE_ENTETE = re.compile(r"<STATION>(?P<station>[^<]*)</STATION>\s*<SENSOR>(?P<capteur>[^<]*)</SENSOR>(?:\s*<DATEFORMAT>(?P<dateformat>[^<]*)</DATEFORMAT>)?", re.IGNORECASE)
RE_CODE = re.compile(r"^\[(?P<code>[^\]]*)\]$")
ENTETE_CSV = ["station","nom_station","capteur","parametre","date","heure","valeur","code"]
FORMAT_DATE_SORTIE = "%d/%m/%Y"
FORMAT_HEURE_SORTIE = "%H:%M:%S"

st.markdown("""
<style>
.last-box {background:linear-gradient(135deg,#00b050 0%,#007a33 100%); color:white; border-radius:14px; padding:18px 22px; margin-bottom:14px; display:flex; justify-content:space-between; align-items:center; gap:12px}
.last-left{flex:1} .last-right{text-align:right; margin-left:20px}
.kpi-box{background:#f8f9fa; border:1px solid #e9ecef; border-radius:12px; padding:14px; text-align:center}
.kpi-val{font-size:22px; font-weight:700; color:#007a33} .kpi-label{font-size:13px; color:#666}
.var-up-big{background:#dcfce7; color:#166534; border-radius:12px; padding:12px 16px; font-size:16px; font-weight:800; border:2px solid #86efac; display:inline-block; min-width:160px; text-align:center}
.var-down-big{background:#fee2e2; color:#991b1b; border-radius:12px; padding:12px 16px; font-size:16px; font-weight:800; border:2px solid #fca5a5; display:inline-block; min-width:160px; text-align:center}
.var-stable-big{background:#ffffff; color:#111827; border-radius:12px; padding:12px 16px; font-size:16px; font-weight:800; border:2px solid #fff; display:inline-block; min-width:160px; text-align:center}
.var-sub{font-size:11px; font-weight:500; opacity:0.8; display:block; margin-top:4px}
@media (max-width: 768px){
  h1{font-size:22px !important}
  .last-box{flex-direction:column; align-items:stretch}
  .last-right{margin-left:0; text-align:center; margin-top:10px}
  .last-right div{width:100% !important; min-width:unset !important}
  [data-testid="column"]{width:100% !important; flex:1 1 100% !important}
  [data-testid="stHorizontalBlock"]{flex-wrap:wrap !important}
}
@media print {
  header, footer, [data-testid="stSidebar"], [data-testid="stHeader"] { display:none !important; }
  .main, .block-container { padding:0 !important; margin:0 !important; max-width:100% !important; }
  body { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
}
</style>
""", unsafe_allow_html=True)

def ecrire_csv(dest, lignes):
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(suffix=".csv", dir=str(dest.parent)); os.close(fd)
    try:
        with open(tmp, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";"); w.writerow(ENTETE_CSV); w.writerows(lignes)
        if dest.exists(): dest.unlink()
        shutil.move(tmp, dest)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)
def lire_texte(path):
    for enc in ("utf-8-sig","cp1252","latin-1"):
        try: return path.read_text(encoding=enc)
        except: continue
    return path.read_text(encoding="utf-8", errors="replace")
def format_python(f): return f.upper().replace("YYYY","%Y").replace("YY","%y").replace("MM","%m").replace("DD","%d")
def formater_date_heure(d,h,fd):
    try: d=datetime.strptime(d, format_python(fd)).strftime(FORMAT_DATE_SORTIE)
    except: pass
    for fmt in ("%H%M%S","%H%M"):
        try: h=datetime.strptime(h.strip(), fmt).strftime(FORMAT_HEURE_SORTIE); break
        except: continue
    return d,h
def lire_mis(chemin):
    lignes=[]; station=capteur=""; fmt_date="YYYYMMDD"
    for ligne in lire_texte(chemin).splitlines():
        ligne=ligne.strip()
        if not ligne: continue
        m=RE_ENTETE.search(ligne)
        if m:
            station=m.group("station").strip(); capteur=m.group("capteur").strip()
            fmt_date=(m.group("dateformat") or "YYYYMMDD").strip(); continue
        champs=[c.strip() for c in ligne.split(";")]
        if len(champs)<3: continue
        date,heure,valeur=champs[0],champs[1],";".join(champs[2:])
        code=""; mc=RE_CODE.match(valeur)
        if mc: code,valeur=mc.group("code"),""
        dt,ht=formater_date_heure(date,heure,fmt_date)
        lignes.append([station, STATIONS_NOMS.get(station,station), capteur, CAPTEURS.get(capteur,capteur), dt, ht, valeur, code])
    return lignes
def trier_sans_doublons(lignes):
    vues,res=set(),[]
    def cle(l):
        try: d=datetime.strptime(l[4], FORMAT_DATE_SORTIE).strftime("%Y%m%d")
        except: d=l[4]
        try: h=datetime.strptime(l[5], FORMAT_HEURE_SORTIE).strftime("%H%M%S")
        except: h=l[5]
        return d+h
    for ligne in sorted(lignes, key=cle):
        sig=tuple(ligne)
        if sig not in vues: vues.add(sig); res.append(ligne)
    return res
def lire_csv_existant(p):
    with open(p, newline="", encoding="utf-8-sig") as f:
        ll=list(csv.reader(f, delimiter=";"))
        return ll[0] if ll else [], ll[1:] if len(ll)>1 else []
def get_last_datetime():
    try:
        if not RELEVES_FINAL.exists(): return None
        df=pd.read_csv(RELEVES_FINAL, sep=';', encoding='utf-8-sig', nrows=5000)
        df.columns=[c.lower().strip() for c in df.columns]
        df["dt"]=pd.to_datetime(df["date"].astype(str)+" "+df["heure"].astype(str), dayfirst=True, errors='coerce')
        return df["dt"].max()
    except: return None

@st.cache_data(ttl=3600, show_spinner=False)
def get_ftp_file_list():
    try:
        ftp = FTP(); ftp.connect(FTP_HOST, FTP_PORT, timeout=10); ftp.login(FTP_USER, FTP_PASS); ftp.set_pasv(True)
        all_files=[]
        for dossier in FTP_DOSSIERS:
            try:
                ftp.cwd(f"/{dossier}"); files=ftp.nlst()
                for f in files:
                    if f.lower().endswith(".mis"): all_files.append((f"/{dossier}", f))
            except: continue
        ftp.quit()
        uniques={Path(f).name:(d,f) for d,f in all_files}
        return list(uniques.values())
    except: return []

def sync_ftp_and_convert():
    if "last_sync_ts" in st.session_state:
        if (time.time() - st.session_state.last_sync_ts) < 3600 and RELEVES_FINAL.exists():
            _, exist = lire_csv_existant(RELEVES_FINAL); return len(exist), 0, True
    DOSSIER_ENTREE.mkdir(exist_ok=True)
    local_files = set(p.name for p in DOSSIER_ENTREE.glob("*.mis")) | set(p.name for p in DOSSIER_ENTREE.glob("*.MIS"))
    last_dt = get_last_datetime()
    if last_dt and pd.notna(last_dt):
        if (datetime.now() - last_dt.to_pydatetime()).total_seconds()/60 < 60:
            st.session_state.last_sync_ts = time.time()
            _, exist = lire_csv_existant(RELEVES_FINAL); return len(exist), 0, True
    all_mis = get_ftp_file_list()
    if not all_mis:
        st.session_state.last_sync_ts = time.time()
        if RELEVES_FINAL.exists():
            _, exist = lire_csv_existant(RELEVES_FINAL); return len(exist), 0, True
        return 0,0,True
    remote_names = {Path(f).name for _, f in all_mis}
    to_download_names = remote_names - local_files
    name_to_dossier = {Path(f).name:d for d,f in all_mis}
    if not to_download_names:
        st.session_state.last_sync_ts = time.time()
        _, exist = lire_csv_existant(RELEVES_FINAL); return len(exist), 0, True
    try:
        ftp = FTP(); ftp.connect(FTP_HOST, FTP_PORT, timeout=15); ftp.login(FTP_USER, FTP_PASS); ftp.set_pasv(True)
        cur_dir=None
        for fname in to_download_names:
            dossier = name_to_dossier[fname]
            try:
                if cur_dir != dossier: ftp.cwd(dossier); cur_dir=dossier
                with open(DOSSIER_ENTREE/fname, 'wb') as lf: ftp.retrbinary(f"RETR {fname}", lf.write, blocksize=65536)
            except: continue
        ftp.quit()
    except: pass
    tous=[]
    for fname in to_download_names:
        src=DOSSIER_ENTREE/fname
        if not src.exists(): continue
        try:
            mes=lire_mis(src); ecrire_csv(DOSSIER_SORTIE/(src.stem+".csv"), mes); tous.extend(mes)
        except: pass
    if RELEVES_FINAL.exists() and tous:
        _, exist = lire_csv_existant(RELEVES_FINAL)
        fusion=trier_sans_doublons(exist+tous); ecrire_csv(RELEVES_FINAL, fusion)
        st.session_state.last_sync_ts=time.time(); return len(fusion), len(to_download_names), False
    elif RELEVES_FINAL.exists():
        _, exist = lire_csv_existant(RELEVES_FINAL); st.session_state.last_sync_ts=time.time(); return len(exist), 0, True
    else:
        tous=trier_sans_doublons(tous); ecrire_csv(RELEVES_FINAL, tous); st.session_state.last_sync_ts=time.time(); return len(tous), len(to_download_names), False

st.title("Hydrométrie du Gabon : DGE")
bar=st.progress(0); txt=st.empty()
txt.text("🔄 Vérification rapide..."); bar.progress(0.3)
try:
    nb_lignes, nb_new, deja_ajour = sync_ftp_and_convert()
    bar.progress(1.0)
    if deja_ajour: txt.success(f"✅ À jour : {nb_lignes} mesures")
    else: txt.success(f"✅ Sync : +{nb_new} fichiers -> {nb_lignes} mesures")
    time.sleep(1); txt.empty(); bar.empty()
except Exception as e:
    bar.empty(); txt.warning(f"Hors-ligne : {e}"); time.sleep(2); txt.empty()

@st.cache_data(show_spinner=False)
def load_gis():
    data={}
    if (BASE/"Limite_Gabon.shp").exists():
        gdf=gpd.read_file(BASE/"Limite_Gabon.shp", engine="pyogrio")
        if gdf.crs: gdf=gdf.to_crs(4326); gdf.columns=[c.lower() for c in gdf.columns]; data["limite"]=gdf
    if (BASE/"Rivieres_Gabon.shp").exists():
        gdf=gpd.read_file(BASE/"Rivieres_Gabon.shp", engine="pyogrio")
        if gdf.crs: gdf=gdf.to_crs(4326); gdf.columns=[c.lower() for c in gdf.columns]; data["rivieres"]=gdf
    if (BASE/"Stations.shp").exists():
        gdf=gpd.read_file(BASE/"Stations.shp", engine="pyogrio")
        if gdf.crs: gdf=gdf.to_crs(4326); gdf.columns=[c.lower() for c in gdf.columns]; data["stations"]=gdf
    return data

@st.cache_data(show_spinner=False)
def load_releves_df():
    df=pd.read_csv(RELEVES_FINAL, sep=';', encoding='utf-8-sig', encoding_errors='ignore')
    df.columns=[c.lower().strip() for c in df.columns]
    df["station"]=df["station"].astype(str).str.strip()
    df["capteur"]=df["capteur"].astype(str).str.strip().str.zfill(4)
    df["datetime"]=pd.to_datetime(df["date"].astype(str)+" "+df["heure"].astype(str), dayfirst=True, errors='coerce')
    df["valeur"]=pd.to_numeric(df["valeur"].astype(str).str.replace(',','.'), errors='coerce')
    df=df.dropna(subset=["datetime","valeur"])
    df["unite_final"]=df["capteur"].map(UNITES)
    return df

gis=load_gis()
try: df=load_releves_df()
except: st.error("Aucun Releves.csv trouvé"); st.stop()

c1,c2,c3=st.columns(3)
with c1:
    def fmt_st(code): return "🌍 Toutes" if code=="Toutes" else f"{code} - {STATIONS_NOMS.get(code,code)}"
    sel_station=st.selectbox("📍 Station", ["Toutes"]+sorted(df["station"].unique().tolist()), format_func=fmt_st)
with c2:
    params=sorted(df["parametre"].dropna().unique().tolist()) if "parametre" in df.columns else sorted(df["capteur"].map(CAPTEURS).unique().tolist())
    default_idx = params.index("Niveau d'eau") if "Niveau d'eau" in params else 0
    sel_param=st.selectbox("📈 Paramètre", params, index=default_idx)
with c3:
    sel_periode=st.selectbox("🗓️ Période", ["Toutes","7 jours","30 jours","Année"], index=0)

df_f=df.copy()
if "parametre" in df.columns: df_f=df_f[df_f["parametre"]==sel_param]
else: df_f=df_f[df_f["capteur"].map(CAPTEURS)==sel_param]
if sel_station!="Toutes": df_f=df_f[df_f["station"]==sel_station]
if sel_periode!="Toutes" and not df_f.empty:
    last=df_f["datetime"].max()
    if sel_periode=="7 jours": df_f=df_f[df_f["datetime"]>=last-timedelta(days=7)]
    elif sel_periode=="30 jours": df_f=df_f[df_f["datetime"]>=last-timedelta(days=30)]
    elif sel_periode=="Année": df_f=df_f[df_f["datetime"]>=last-timedelta(days=365)]

col_gauche, col_droite = st.columns([1.1,1.4], gap="medium")
with col_gauche:
    st.subheader("🗺️ Carte")
    layers=[]
    if "limite" in gis:
        for geom in gis["limite"].geometry:
            if geom.geom_type=="Polygon": layers.append(pdk.Layer("PolygonLayer", data=[{"poly":[list(geom.exterior.coords)]}], get_polygon="poly", get_fill_color=[180,180,180,40], get_line_color=[27,94,32,255], line_width_min_pixels=2.5))
            elif geom.geom_type=="MultiPolygon":
                for g in geom.geoms: layers.append(pdk.Layer("PolygonLayer", data=[{"poly":[list(g.exterior.coords)]}], get_polygon="poly", get_fill_color=[180,180,180,40], get_line_color=[27,94,32,255], line_width_min_pixels=2.5))
    if "rivieres" in gis and not gis["rivieres"].empty:
        paths=[]
        for geom in gis["rivieres"].geometry:
            if geom is None: continue
            if geom.geom_type=="LineString": paths.append({"path":list(geom.coords)})
            elif geom.geom_type=="MultiLineString":
                for line in geom.geoms: paths.append({"path":list(line.coords)})
        if paths: layers.append(pdk.Layer("PathLayer", data=paths, get_path="path", get_color=[30,120,255,220], width_min_pixels=2.5, joint_rounded=True))
    pts_all, pts_sel=[], []
    if "stations" in gis:
        for _, r in gis["stations"].iterrows():
            try:
                lat, lon=r.geometry.y, r.geometry.x
                code=str(r.iloc[0])
                for c in r.index:
                    if "code" in str(c).lower() or "station" in str(c).lower(): code=str(r[c]); break
                item={"lat":lat,"lon":lon,"name":f"{code} - {STATIONS_NOMS.get(code,code)}","code":code}
                if sel_station!="Toutes" and code==sel_station: pts_sel.append(item)
                else: pts_all.append(item)
            except: pass
        if pts_all: layers.append(pdk.Layer("ScatterplotLayer", data=pts_all, get_position='[lon, lat]', get_color='[255,0,0,230]', get_radius=7000, radius_min_pixels=6, pickable=True))
        if pts_sel:
            layers.append(pdk.Layer("ScatterplotLayer", data=pts_sel, get_position='[lon, lat]', get_color='[0,176,80,50]', get_radius=30000, radius_min_pixels=28, pickable=False))
            layers.append(pdk.Layer("ScatterplotLayer", data=pts_sel, get_position='[lon, lat]', get_color='[0,176,80,255]', get_radius=10000, radius_min_pixels=10, pickable=True))
    if "limite" in gis:
        b=gis["limite"].total_bounds; lat_c,lon_c=(b[1]+b[3])/2,(b[0]+b[2])/2
        view=pdk.ViewState(latitude=pts_sel[0]["lat"], longitude=pts_sel[0]["lon"], zoom=6) if pts_sel else pdk.ViewState(latitude=lat_c, longitude=lon_c, zoom=5.2)
    else: view=pdk.ViewState(latitude=-0.8, longitude=11.8, zoom=5.2)
    deck=pdk.Deck(layers=layers, initial_view_state=view, map_style=None, tooltip={"text":"{name}"})
    st.pydeck_chart(deck, height=420)

with col_droite:
    st.subheader("📊 Tableau de bord")
    if df_f.empty: st.warning("Pas de données")
    else:
        df_s=df_f.sort_values("datetime")
        last_row=df_s.iloc[-1]; unite=last_row["unite_final"] or ""
        var_html=""
        if len(df_s)>=2:
            prev=df_s.iloc[-2]; delta=last_row["valeur"]-prev["valeur"]
            if abs(delta)<0.001: var_html=f'<div class="var-stable-big">→ 0.00 {unite}<span class="var-sub">Stable vs {prev["heure"]}<br>{prev["valeur"]:.2f} {unite}</span></div>'
            elif delta>0: var_html=f'<div class="var-up-big">↗ +{delta:.2f} {unite}<span class="var-sub">Hausse vs {prev["heure"]}<br>{prev["valeur"]:.2f} {unite}</span></div>'
            else: var_html=f'<div class="var-down-big">↘ {delta:.2f} {unite}<span class="var-sub">Baisse vs {prev["heure"]}<br>{prev["valeur"]:.2f} {unite}</span></div>'
        else: var_html='<div class="var-stable-big">1ère valeur</div>'
        st.markdown(f'''
        <div class="last-box"><div class="last-left"><div style="font-size:13px;opacity:0.9">Dernière - {STATIONS_NOMS.get(str(last_row["station"]), last_row["station"])} / {last_row["parametre"] if "parametre" in last_row else CAPTEURS.get(last_row["capteur"],"")}</div>
        <div style="font-size:28px;font-weight:800">{last_row["valeur"]} {unite}</div><div style="opacity:0.9">{last_row["date"]} {last_row["heure"]}</div></div>
        <div class="last-right">{var_html}</div></div>''', unsafe_allow_html=True)
        vmin,vmax,vmoy=df_f["valeur"].min(), df_f["valeur"].max(), df_f["valeur"].mean()
        if last_row["capteur"]=="0002":
            k1,k2,k3,k4=st.columns(4)
            with k1: st.markdown(f'<div class="kpi-box"><div class="kpi-label">Min</div><div class="kpi-val">{vmin:.2f}</div></div>', unsafe_allow_html=True)
            with k2: st.markdown(f'<div class="kpi-box"><div class="kpi-label">Max</div><div class="kpi-val">{vmax:.2f}</div></div>', unsafe_allow_html=True)
            with k3: st.markdown(f'<div class="kpi-box"><div class="kpi-label">Moy</div><div class="kpi-val">{vmoy:.2f}</div></div>', unsafe_allow_html=True)
            with k4: st.markdown(f'<div class="kpi-box"><div class="kpi-label">Total</div><div class="kpi-val">{df_f["valeur"].sum():.1f}</div></div>', unsafe_allow_html=True)
        else:
            k1,k2,k3=st.columns(3)
            with k1: st.markdown(f'<div class="kpi-box"><div class="kpi-label">Min</div><div class="kpi-val">{vmin:.2f} {unite}</div></div>', unsafe_allow_html=True)
            with k2: st.markdown(f'<div class="kpi-box"><div class="kpi-label">Max</div><div class="kpi-val">{vmax:.2f} {unite}</div></div>', unsafe_allow_html=True)
            with k3: st.markdown(f'<div class="kpi-box"><div class="kpi-label">Moy</div><div class="kpi-val">{vmoy:.2f} {unite}</div></div>', unsafe_allow_html=True)
        fig=px.line(df_s, x="datetime", y="valeur")
        fig.update_layout(xaxis_title="Période", yaxis_title=f"{sel_param} ({unite})", height=340, margin=dict(l=10,r=10,t=20,b=10))
        st.plotly_chart(fig, use_container_width=True)

st.divider()
st.subheader("📋 Dernières valeurs")
if not df_f.empty:
    st.dataframe(df_f.sort_values("datetime", ascending=False).head(10), use_container_width=True, height=350)

st.divider()
st.subheader("🖨️ Imprimer en paysage")
st.caption("Paysage uniquement - Coche 'Arrière-plans graphiques' pour garder les couleurs.")

components.html("""
<style>
  .print-wrap{display:flex; gap:12px; justify-content:center; flex-wrap:wrap; margin:10px 0 20px 0}
  .pbtn{border:none; padding:14px 22px; border-radius:12px; font-weight:800; cursor:pointer; color:white; font-size:15px; min-width:180px}
  .p-a4{background:linear-gradient(135deg,#00b050,#007a33)}
  .p-a3{background:linear-gradient(135deg,#2563eb,#1e40af)}
  @media(max-width:768px){ .pbtn{width:100%} }
</style>
<div class="print-wrap">
  <button class="pbtn p-a4" onclick="printPage('A4 landscape')">🖨️ Imprimer A4 Paysage</button>
  <button class="pbtn p-a3" onclick="printPage('A3 landscape')">🖨️ Imprimer A3 Paysage</button>
</div>
<script>
function printPage(size){
  let style = document.getElementById('print-style');
  if(!style){ style=document.createElement('style'); style.id='print-style'; document.head.appendChild(style); }
  style.innerHTML = `
    @page { size: ${size}; margin: 10mm; }
    @media print {
      [data-testid="stSidebar"], [data-testid="stHeader"], header, footer { display:none !important; }
      .print-wrap, button { display:none !important; }
      .block-container { padding-top:0 !important; max-width:100% !important; }
    }
  `;
  setTimeout(()=>{ window.parent.print(); }, 250);
}
</script>
""", height=90)
