import requests
import json
import re
import time
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─── CONFIG ───
CAMERA_OUTPUT = "camera.json"
RADAR_OUTPUT  = "radars.json"

# ─── SOURCE RADARS : radars-auto.com scraping ───
DEPARTEMENTS = [
    "ain","aisne","allier","alpes-de-haute-provence","alpes-maritimes",
    "ardeche","ardennes","ariege","aube","aude","aveyron","bas-rhin",
    "bouches-du-rhone","calvados","cantal","charente","charente-maritime",
    "cher","correze","corse-du-sud","haute-corse","cote-d-or","cotes-d-armor",
    "creuse","dordogne","doubs","drome","essonne","eure","eure-et-loir",
    "finistere","gard","haute-garonne","gers","gironde","herault",
    "ille-et-vilaine","indre","indre-et-loire","isere","jura","landes",
    "loir-et-cher","loire","haute-loire","loire-atlantique","loiret",
    "lot","lot-et-garonne","lozere","maine-et-loire","manche","marne",
    "haute-marne","mayenne","meurthe-et-moselle","meuse","morbihan","moselle",
    "nievre","nord","oise","orne","pas-de-calais","puy-de-dome",
    "pyrenees-atlantiques","hautes-pyrenees","pyrenees-orientales","haut-rhin",
    "rhone","haute-saone","saone-et-loire","sarthe","savoie","haute-savoie",
    "seine-maritime","seine-et-marne","seine-st-denis","deux-sevres","somme",
    "tarn","tarn-et-garonne","var","vaucluse","vendee","vienne","haute-vienne",
    "vosges","yonne","territoire-de-belfort","hauts-de-seine",
    "val-de-marne","val-d-oise","paris","yvelines"
]
DEPARTEMENTS = list(dict.fromkeys(DEPARTEMENTS))

SCRAPE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9",
    "Referer": "https://www.radars-auto.com/",
}

ICON_TO_TYPE = {
    "image1":  "fixe",
    "image2":  "fixe",
    "image3":  "fixe",
    "image3doublesens": "double_sens",
    "image4":  "fixe",
    "image5":  "double_face",
    "image6":  "fixe",
    "image12": "feu_rouge",
    "image18": "feu_vitesse",
    "image20": "troncon",
    "image30": "mobile",
    "image41": "mobile",
    "image42": "tourelle",
    "image43": "urbain",        # radar urbain (nouvelle génération urbaine)
    "image50": "voiture",       # voiture radar embarquée
    "image53": "voiture",       # voiture radar (autre modèle)
    "image60": "passage_niveau",
    "image80": None,            # pédagogique → ignoré
    "image90": "double_sens",
    "image99": "fixe",
}

# Regex markers (un par radar)
RE_MARKER = re.compile(
    r"L\.marker\(\[([+-]?\d+\.\d+),\s*([+-]?\d+\.\d+)\],\s*\{icon:\s*(\w+)\}\)"
    r"\.addTo\(mymap\)\.bindPopup\('(.*?)'\s*,\s*\{minWidth",
    re.DOTALL
)
# Regex tronçons : var latlngsXXX = [ [lat,lng],[lat,lng],... ];
RE_TRONCON = re.compile(
    r"var latlngs(\d+)\s*=\s*\[\s*((?:\[[\d.,]+\](?:,\s*)?)+)\s*\]",
    re.DOTALL
)
RE_LATLON_PAIR = re.compile(r"\[([\d.+-]+),([\d.+-]+)\]")

RE_VITESSE  = re.compile(r'picto-vitesse-(\d+)', re.IGNORECASE)
RE_POPUP_ROUTE = re.compile(r'<strong>([^<]+)<br /><br />([^<]*?)\s*-\s*([^<]+?)<br />')
RE_POPUP_SENS  = re.compile(r'<strong>Sens\s*:\s*</strong>([^<]+)')
RE_POPUP_ID    = re.compile(r'id_radar=(\d+)')


# ─── CAMERAS : OpenStreetMap Overpass API ───


def fetch_kml_cameras() -> list[dict]:
    """
    Source secondaire : KML Google Maps (base originale du projet).
    """
    MAP_MID = "1B24mI0caHQtcN4IjgWfAidDev2eN-_FG"
    KML_URL = f"https://www.google.com/maps/d/u/0/kml?mid={MAP_MID}&forcekml=1"
    import xml.etree.ElementTree as ET

    logger.info("  → KML Google Maps (caméras Paris)...")
    try:
        resp = requests.get(KML_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
        resp.raise_for_status()
        ns = {"kml": "http://www.opengis.net/kml/2.2"}
        root = ET.fromstring(resp.content)
        cameras = []
        for pm in root.findall(".//kml:Placemark", ns):
            name_el = pm.find("kml:name", ns)
            desc_el = pm.find("kml:description", ns)
            point = pm.find(".//kml:coordinates", ns)
            if point is None:
                continue
            coords = point.text.strip().split(",")
            if len(coords) < 2:
                continue
            name = re.sub(r'<[^<]+?>', '', name_el.text if (name_el is not None and name_el.text) else "Caméra")
            desc = re.sub(r'<[^<]+?>', '', desc_el.text if (desc_el is not None and desc_el.text) else "")
            cameras.append({
                "nom": name.strip(),
                "latitude": float(coords[1]),
                "longitude": float(coords[0]),
                "direction": "Non spécifiée",
                "source": "KML-Paris"
            })
        logger.info(f"  ✅ {len(cameras)} caméras KML")
        return cameras
    except Exception as e:
        logger.warning(f"  ⚠️ KML erreur : {e}")
        return []


def fetch_umap_cameras_marseille() -> list[dict]:
    """
    Source : uMap OpenStreetMap — Caméras de vidéo-surveillance à Marseille (map_id=809).
    Récupère les datalayers via l'API uMap GeoJSON.
    """
    MAP_ID = 809
    DATALAYER_IDS = [
        "e6318e78-1ce9-4426-ba69-5a6658e9cd07",  # Caméras en projet
        "ac0e8a3c-2d0e-4cdf-a83d-7daa0eaf9df9",  # Caméras actuellement installées
        "942cc027-c9b6-4872-9081-5d4072192049",  # Layer 1
    ]
    cameras = []
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}

    logger.info("  → uMap Marseille (caméras surveillance)...")
    for dl_id in DATALAYER_IDS:
        url = f"https://umap.openstreetmap.fr/fr/datalayer/{MAP_ID}/{dl_id}/"
        try:
            resp = requests.get(url, headers=headers, timeout=20)
            resp.raise_for_status()
            data = resp.json()
            features = data.get("features", [])
            for feat in features:
                geom = feat.get("geometry", {})
                props = feat.get("properties", {})
                if geom.get("type") != "Point":
                    continue
                coords = geom.get("coordinates", [])
                if len(coords) < 2:
                    continue
                name = props.get("name") or props.get("nom") or "Caméra Marseille"
                name = re.sub(r'<[^<]+?>', '', str(name)).strip()
                cameras.append({
                    "nom": name,
                    "latitude": float(coords[1]),
                    "longitude": float(coords[0]),
                    "direction": props.get("direction", "Non spécifiée"),
                    "source": "uMap-Marseille"
                })
        except Exception as e:
            logger.warning(f"  ⚠️ uMap datalayer {dl_id}: {e}")

    logger.info(f"  ✅ {len(cameras)} caméras uMap Marseille")
    return cameras


def update_cameras():
    logger.info("📷 Mise à jour des caméras...")
    kml_cams = fetch_kml_cameras()
    marseille_cams = fetch_umap_cameras_marseille()
    all_cams = kml_cams + marseille_cams
    with open(CAMERA_OUTPUT, "w", encoding="utf-8") as f:
        json.dump(all_cams, f, indent=2, ensure_ascii=False)
    logger.info(f"✅ {len(all_cams)} caméras sauvegardées ({len(kml_cams)} Paris + {len(marseille_cams)} Marseille)")


# ─── RADARS ───


def scrape_dept(dept_slug: str) -> tuple[list[dict], list[dict]]:
    """
    Retourne (radars, troncons_polylines).
    troncons_polylines = liste de {id, coords: [[lat,lng],...]}
    """
    url = f"https://www.radars-auto.com/emplacements/{dept_slug}/"
    try:
        resp = requests.get(url, headers=SCRAPE_HEADERS, timeout=15)
        resp.raise_for_status()
        html = resp.text
    except Exception as e:
        logger.warning(f"  ⚠️ {dept_slug}: {e}")
        return [], []

    radars = []
    for m in RE_MARKER.finditer(html):
        lat_s, lng_s, icon_var, popup = m.group(1), m.group(2), m.group(3), m.group(4)
        if icon_var == "pictoleurre":
            continue
        rtype = ICON_TO_TYPE.get(icon_var)
        if rtype is None:
            continue
        vm = RE_VITESSE.search(popup)
        vitesse = int(vm.group(1)) if vm else None
        pm = RE_POPUP_ROUTE.search(popup)
        route   = pm.group(2).strip() if pm else ""
        commune = pm.group(3).strip() if pm else ""
        sm = RE_POPUP_SENS.search(popup)
        sens = sm.group(1).strip() if sm else ""
        idm = RE_POPUP_ID.search(popup)
        radar_id = int(idm.group(1)) if idm else None
        radars.append({
            "lat": float(lat_s), "lng": float(lng_s),
            "type": rtype, "vitesse": vitesse,
            "route": route, "commune": commune, "sens": sens,
            "id": radar_id, "source": "radars-auto.com"
        })

    # ─ Extraire les polylignes de tronçons (début → fin)
    troncons = []
    for tm in RE_TRONCON.finditer(html):
        zone_id = tm.group(1)
        raw_pairs = tm.group(2)
        coords = [[float(lat), float(lng)]
                  for lat, lng in RE_LATLON_PAIR.findall(raw_pairs)]
        if len(coords) >= 2:
            troncons.append({
                "id": zone_id,
                "debut": coords[0],
                "fin": coords[-1],
                "coords": coords   # trajet complet
            })

    return radars, troncons


def update_radars():
    logger.info("📡 Mise à jour des radars...")

    logger.info("  → Scraping radars-auto.com...")
    all_radars = []
    all_troncons = []
    for i, dept in enumerate(DEPARTEMENTS):
        radars, troncons = scrape_dept(dept)
        if radars:
            logger.info(f"     [{i+1}/{len(DEPARTEMENTS)}] {dept}: {len(radars)} radars, {len(troncons)} tronçons")
            all_radars.extend(radars)
            all_troncons.extend(troncons)
        time.sleep(0.4)

    logger.info(f"  → {len(all_radars)} radars, {len(all_troncons)} tronçons")

    # Dédupliquer les tronçons par id
    seen_ids = set()
    unique_troncons = []
    for t in all_troncons:
        if t["id"] not in seen_ids:
            seen_ids.add(t["id"])
            unique_troncons.append(t)

    output = {"radars": all_radars, "troncons": unique_troncons}
    with open(RADAR_OUTPUT, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, separators=(",", ":"))

    logger.info(f"✅ {len(all_radars)} radars + {len(unique_troncons)} tronçons sauvegardés")


if __name__ == "__main__":
    print("=== MISE À JOUR GLOBALE ===\n")
    update_cameras()
    print("-" * 40)
    update_radars()
    print("\n=== TERMINÉ ===")
