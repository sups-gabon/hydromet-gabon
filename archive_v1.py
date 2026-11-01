from pathlib import Path
import shutil
from datetime import datetime

BASE = Path(__file__).parent
date = datetime.now().strftime("%Y-%m-%d_%Hh%M")
dest = BASE / "Archives" / f"V1_{date}"
dest.mkdir(parents=True, exist_ok=True)

# Fichiers à archiver
files_to_save = ["app.py", "Releves.csv", "requirements.txt", "Stations.shp", "Stations.shx", "Stations.dbf", "Stations.prj", "Limite_Gabon.shp", "Rivieres_Gabon.shp"]

for name in files_to_save:
    src = BASE / name
    if src.exists():
        shutil.copy2(src, dest / name)

# Crée aussi un README
(dest / "README_V1.txt").write_text(f"""Archive V1 - Hydrométrie DGE
Date: {date}
Contenu:
- Sync FTP rapide optimisée (cache 1h)
- Carte gris clair + rivières
- Dashboard variation verte/rouge/blanc
- Paramètre par défaut: Niveau d'eau
- Impression A4/A3 paysage
- Responsive mobile/tablette
Version stable avant passage V2 Analyse & Exploitation
""", encoding="utf-8")

print(f"✅ V1 archivée dans : {dest}")
