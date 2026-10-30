# ... garde tout le début identique jusqu'à load_releves ...

@st.cache_data(ttl=600)
def load_releves():
    df_final = None
    if RELEVES_FINAL.exists():
        try:
            df=pd.read_csv(RELEVES_FINAL, sep=';', encoding='utf-8-sig', errors='ignore')
            df.columns=[c.lower().strip() for c in df.columns]
            df["station"]=df["station"].astype(str).str.strip()
            if "capteur" in df.columns:
                df["capteur"]=df["capteur"].astype(str).str.strip().str.zfill(4)
            if "date" in df.columns and "heure" in df.columns:
                df["datetime"]=pd.to_datetime(df["date"].astype(str)+" "+df["heure"].astype(str), dayfirst=True, errors='coerce')
            df["valeur"]=pd.to_numeric(df["valeur"].astype(str).str.replace(',','.'), errors='coerce')
            df_final=df
        except Exception as e:
            st.warning(f"Releves.csv illisible: {e}")

    # Fallback local .mis
    try:
        if DOSSIER_ENTREE.exists():
            tous=[]
            for mis in list(DOSSIER_ENTREE.glob("*.mis")) + list(DOSSIER_ENTREE.glob("*.MIS")):
                tous.extend(lire_mis(mis))
            if tous:
                df_mis = pd.DataFrame(tous, columns=ENTETE_CSV)
                df_mis["station"]=df_mis["station"].astype(str)
                df_mis["datetime"]=pd.to_datetime(df_mis["date"].astype(str)+" "+df_mis["heure"].astype(str), dayfirst=True, errors='coerce')
                df_mis["valeur"]=pd.to_numeric(df_mis["valeur"].astype(str).str.replace(',','.'), errors='coerce')
                if df_final is None:
                    df_final = df_mis
                else:
                    df_final = pd.concat([df_final, df_mis], ignore_index=True).drop_duplicates()
    except: pass
    return df_final

gis_data=load_gis()
df=load_releves()

# --- NE PLUS BLOQUER SI PAS DE DONNEES ---
if df is None or df.empty:
    st.warning("⚠️ Mode Carte uniquement : Aucune donnée FTP pour le moment. La carte Gabon s'affiche ci-dessous. Ajoute Releves.csv à ton GitHub pour voir les graphiques.")
    # Affiche quand même la carte
    col_gauche = st.columns(1)[0]
    with col_gauche:
        st.subheader("🗺️ Gabon - Stations")
        layers=[]
        if "limite" in gis_data:
            for geom in gis_data["limite"].geometry:
                try:
                    if geom.geom_type=="Polygon": layers.append(pdk.Layer("PolygonLayer", data=[{"polygon":[list(geom.exterior.coords)]}], get_polygon="polygon[0]", get_fill_color=[0,0,0,6], get_line_color=[0,0,0,180], line_width_min_pixels=2))
                except: pass
        if "rivieres" in gis_data:
            lines=[{"path":list(g.coords)} for g in gis_data["rivieres"].geometry if g.geom_type=="LineString"]
            if lines: layers.append(pdk.Layer("PathLayer", data=lines, get_path="path", get_color=[0,110,255,120], width_min_pixels=2))
        if "stations" in gis_data:
            pts=[]
            for _, row in gis_data["stations"].iterrows():
                try:
                    pts.append({"lat":row.geometry.y, "lon":row.geometry.x, "full":str(row.iloc[0])})
                except: pass
            if pts: layers.append(pdk.Layer("ScatterplotLayer", data=pts, get_position='[lon, lat]', get_color='[255, 0, 0, 200]', get_radius=4000, radius_min_pixels=5, pickable=True))
        deck = pdk.Deck(layers=layers, initial_view_state=pdk.ViewState(latitude=-0.5, longitude=11.8, zoom=5.2), map_style="light", tooltip={"text": "{full}"})
        st.pydeck_chart(deck, height=600)
    
    st.info(f"Debug: Releves.csv existe ? {RELEVES_FINAL.exists()} | DonneesEntrees existe ? {DOSSIER_ENTREE.exists()} | Fichiers dedans: {len(list(DOSSIER_ENTREE.glob('*'))) if DOSSIER_ENTREE.exists() else 0}")
    st.stop()

# --- ICI TON CODE NORMAL SI DF EXISTE (le reste de ton dashboard) ---
