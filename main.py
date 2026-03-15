import json
import os
import atexit
import logging
from flask import Flask, Response, jsonify
from apscheduler.schedulers.background import BackgroundScheduler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    import auto_update
except ImportError:
    logger.warning("⚠️ auto_update.py non trouvé.")

app = Flask(__name__)

FILE_CAMERAS = "camera.json"
FILE_RADARS  = "radars.json"
UPDATE_INTERVAL_MINUTES = 15

# ─── État global des mises à jour ───
import datetime
update_status = {
    "last_success": None,       # ISO string de la dernière maj complète
    "last_attempt": None,       # ISO string de la dernière tentative
    "running": False,           # True pendant l'exécution
    "errors": [],               # Liste des dernières erreurs (max 10)
    "radars_count": 0,
    "cameras_count": 0,
    "next_run": None,           # ISO string de la prochaine exécution
}

def _iso_now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def scheduled_update():
    global update_status
    update_status["running"] = True
    update_status["last_attempt"] = _iso_now()
    errors = []
    radars_ok = False
    cameras_ok = False
    try:
        import auto_update
        try:
            auto_update.update_radars()
            radars_ok = True
        except Exception as e:
            msg = f"Radars : {e}"
            logger.error(f"❌ {msg}")
            errors.append({"time": _iso_now(), "msg": msg})
        try:
            auto_update.update_cameras()
            cameras_ok = True
        except Exception as e:
            msg = f"Caméras : {e}"
            logger.error(f"❌ {msg}")
            errors.append({"time": _iso_now(), "msg": msg})
    except Exception as e:
        msg = f"Import auto_update : {e}"
        logger.error(f"❌ {msg}")
        errors.append({"time": _iso_now(), "msg": msg})

    # Compter les données chargées
    try:
        if os.path.exists(FILE_RADARS):
            with open(FILE_RADARS, 'r', encoding='utf-8') as f:
                d = json.load(f)
            update_status["radars_count"] = len(d.get("radars", d) if isinstance(d, dict) else d)
    except Exception:
        pass
    try:
        if os.path.exists(FILE_CAMERAS):
            with open(FILE_CAMERAS, 'r', encoding='utf-8') as f:
                update_status["cameras_count"] = len(json.load(f))
    except Exception:
        pass

    update_status["errors"] = (errors + update_status["errors"])[:10]
    update_status["running"] = False
    if not errors:
        update_status["last_success"] = _iso_now()

    # Calculer prochaine exécution
    try:
        job = scheduler.get_jobs()[0]
        update_status["next_run"] = job.next_run_time.isoformat() if job.next_run_time else None
    except Exception:
        pass

scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(func=scheduled_update, trigger="interval", minutes=UPDATE_INTERVAL_MINUTES, id="main_update")
scheduler.start()
atexit.register(lambda: scheduler.shutdown())

@app.route('/api/radars')
def api_radars():
    if os.path.exists(FILE_RADARS):
        with open(FILE_RADARS, 'r', encoding='utf-8') as f:
            data = json.load(f)
        # Nouveau format : {radars:[...], troncons:[...]}
        if isinstance(data, dict):
            return jsonify(data)
        # Ancien format : liste directe
        return jsonify({"radars": data, "troncons": []})
    return jsonify({"radars": [], "troncons": []})

@app.route('/api/cameras')
def api_cameras():
    if os.path.exists(FILE_CAMERAS):
        with open(FILE_CAMERAS, 'r', encoding='utf-8') as f:
            return jsonify(json.load(f))
    return jsonify([])

@app.route('/health')
def health():
    return jsonify({"status": "ok"})

@app.route('/api/status')
def api_status():
    try:
        job = scheduler.get_jobs()[0]
        update_status["next_run"] = job.next_run_time.isoformat() if job.next_run_time else None
    except Exception:
        pass
    return jsonify(update_status)

@app.route('/api/force-update', methods=['POST'])
def api_force_update():
    import threading
    if update_status.get("running"):
        return jsonify({"status": "already_running"}), 409
    t = threading.Thread(target=scheduled_update, daemon=True)
    t.start()
    return jsonify({"status": "started"})

@app.route('/')
def index():
    html = r"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="RadatBot">
<meta name="theme-color" content="#0d0d0f">
<title>RadatBot France</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css"/>
<link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;600;700;800&display=swap" rel="stylesheet">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js"></script>
<style>
  :root {
    --bg:#f2f2f7; --surface:rgba(255,255,255,.88); --surface2:rgba(255,255,255,.97);
    --border:rgba(0,0,0,.09); --accent:#007aff; --green:#34c759;
    --danger:#ff3b30; --warn:#ff9500; --text:#1c1c1e; --text2:rgba(60,60,67,.55);
    --blur:blur(20px) saturate(180%); --r:14px; --font:'Outfit',-apple-system,sans-serif;
    --shadow:0 4px 24px rgba(0,0,0,.13);
  }
  body.dark {
    --bg:#1c1c1e; --surface:rgba(28,28,30,.92); --surface2:rgba(36,36,40,.97);
    --border:rgba(255,255,255,.08); --text:#f5f5f7; --text2:rgba(245,245,247,.5);
    --shadow:0 4px 24px rgba(0,0,0,.5);
  }
  *,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
  html,body{height:100%;width:100%;overflow:hidden;background:var(--bg);font-family:var(--font);transition:background .4s}
  #map{position:absolute;inset:0;z-index:1}

  /* STATUS PILL */
  #status-pill{
    position:absolute;top:16px;left:50%;transform:translateX(-50%);
    z-index:1000;display:flex;align-items:center;gap:8px;
    background:var(--surface);backdrop-filter:var(--blur);
    border:1px solid var(--border);border-radius:100px;
    padding:7px 16px 7px 12px;pointer-events:none;
    box-shadow:var(--shadow);
  }
  #vis-dot{width:10px;height:10px;border-radius:50%;background:var(--green);box-shadow:0 0 6px var(--green);transition:.3s}
  #vis-dot.orange{background:var(--warn);box-shadow:0 0 6px var(--warn)}
  #vis-dot.red{background:var(--danger);box-shadow:0 0 10px var(--danger);animation:blink .5s infinite alternate}
  #vis-label{font-size:13px;font-weight:600;color:var(--text);letter-spacing:.2px}
  @keyframes blink{from{opacity:1}to{opacity:.35}}

  /* ALERT BANNER */
  #alert-banner{
    position:absolute;top:56px;left:50%;transform:translateX(-50%);
    z-index:1001;display:none;
    background:linear-gradient(135deg,#ff3b30,#c0001a);
    border:1px solid rgba(255,255,255,.18);border-radius:20px;
    padding:13px 24px;text-align:center;min-width:190px;
    box-shadow:0 8px 32px rgba(255,59,48,.45);
  }
  #alert-banner.show{display:block;animation:slideDown .28s cubic-bezier(.4,0,.2,1)}
  @keyframes slideDown{from{opacity:0;transform:translateX(-50%) translateY(-12px)}to{opacity:1;transform:translateX(-50%) translateY(0)}}
  #alert-type{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:1.5px;color:rgba(255,255,255,.75);margin-bottom:2px}
  #alert-dist{font-size:30px;font-weight:800;color:#fff;line-height:1.05}
  #alert-speed{font-size:12px;color:rgba(255,255,255,.65);margin-top:3px}

  /* FABS */
  #fab-group{position:absolute;right:16px;top:50%;transform:translateY(-50%);z-index:1000;display:flex;flex-direction:column;gap:10px}
  .fab{
    width:46px;height:46px;border-radius:13px;
    background:var(--surface2);backdrop-filter:var(--blur);
    border:1px solid var(--border);display:flex;align-items:center;
    justify-content:center;cursor:pointer;
    transition:transform .15s,background .2s,box-shadow .2s;
    box-shadow:var(--shadow);color:var(--text2);
  }
  .fab:active{transform:scale(.91)}
  .fab.active{background:var(--accent);border-color:var(--accent);color:#fff;box-shadow:0 4px 20px rgba(0,122,255,.4)}
  .fab svg{width:20px;height:20px;flex-shrink:0}

  /* DRAWER */
  #settings-drawer{
    position:absolute;right:70px;top:50%;transform:translateY(-50%);
    z-index:1000;width:248px;
    background:var(--surface2);backdrop-filter:var(--blur);
    border:1px solid var(--border);border-radius:var(--r);
    padding:16px;display:none;flex-direction:column;gap:13px;
    box-shadow:0 8px 40px rgba(0,0,0,.18);
  }
  #settings-drawer.open{display:flex;animation:fadeIn .2s ease}
  @keyframes fadeIn{from{opacity:0;transform:translateY(-50%) translateX(10px)}to{opacity:1;transform:translateY(-50%) translateX(0)}}
  .drawer-title{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:1.2px;color:var(--text2)}
  .setting-row{display:flex;justify-content:space-between;align-items:center;gap:8px}
  .setting-label{font-size:14px;font-weight:600;color:var(--text)}
  .setting-sub{font-size:11px;color:var(--text2);margin-top:1px}
  .divider{height:1px;background:var(--border)}

  /* iOS TOGGLE */
  .toggle{position:relative;width:44px;height:26px;flex-shrink:0}
  .toggle input{opacity:0;width:0;height:0}
  .toggle-track{position:absolute;inset:0;border-radius:13px;background:#ddd;cursor:pointer;transition:.25s}
  body.dark .toggle-track{background:#3a3a3c}
  .toggle input:checked~.toggle-track{background:var(--green)}
  .toggle-thumb{position:absolute;top:3px;left:3px;width:20px;height:20px;border-radius:50%;background:#fff;box-shadow:0 1px 4px rgba(0,0,0,.3);pointer-events:none;transition:transform .25s cubic-bezier(.4,0,.2,1)}
  .toggle input:checked~.toggle-thumb{transform:translateX(18px)}

  /* STATUS PANEL */
  #status-panel{display:flex;flex-direction:column;gap:6px}
  .status-row{display:flex;justify-content:space-between;align-items:center;gap:8px;font-size:12px}
  .status-key{color:var(--text2);font-weight:600}
  .status-val{color:var(--text);font-weight:700;text-align:right;max-width:140px;word-break:break-word}
  .status-val.ok{color:var(--green)}
  .status-val.err{color:var(--danger)}
  .status-val.running{color:var(--warn)}
  #error-list{display:flex;flex-direction:column;gap:4px;max-height:100px;overflow-y:auto}
  .error-item{font-size:11px;color:var(--danger);background:rgba(255,59,48,.08);border-radius:6px;padding:4px 8px;word-break:break-word}
  .error-time{font-size:9px;color:var(--text2);display:block;margin-top:1px}
  .btn-force{background:rgba(0,122,255,.12);color:var(--accent);border:1px solid rgba(0,122,255,.2)}
  .btn-force:hover{background:rgba(0,122,255,.2)}
  .btn-force:disabled{opacity:.4;cursor:not-allowed}
  .btn-primary{background:var(--accent);color:#fff}
  .btn-secondary{background:rgba(120,120,128,.12);color:var(--text)}
  body.dark .btn-secondary{background:rgba(255,255,255,.08)}
  .btn-danger{background:rgba(255,59,48,.12);color:var(--danger)}

  /* iOS pseudo-fullscreen */
  body.ios-fullscreen{position:fixed;inset:0;overflow:hidden}
  body.ios-fullscreen #map{position:fixed;inset:0;z-index:1}
  body.ios-fullscreen #fab-group,body.ios-fullscreen #speedo,body.ios-fullscreen #data-badge,
  body.ios-fullscreen #status-pill,body.ios-fullscreen #alert-banner{z-index:9500}

  /* Threshold badges */
  .thresh-display{display:flex;flex-direction:column;gap:8px;width:100%}
  .thresh-top{display:flex;justify-content:space-between;align-items:center}
  .thresh-badges{display:flex;gap:5px;flex-wrap:wrap}
  .thresh-badge{font-size:11px;font-weight:700;padding:4px 9px;border-radius:20px;border:1px solid var(--border);color:var(--text2);cursor:pointer;background:var(--surface);transition:.15s;}
  .thresh-badge.sel{background:var(--accent);border-color:var(--accent);color:#fff}
  input[type=range]{width:100%;accent-color:var(--accent)}

  /* SPEEDO */
  #speedo{
    position:absolute;bottom:32px;left:20px;z-index:1000;
    background:var(--surface);backdrop-filter:var(--blur);
    border:1px solid var(--border);border-radius:18px;
    padding:12px 20px;text-align:center;min-width:90px;
    box-shadow:var(--shadow);
  }
  #speed-val{font-size:36px;font-weight:800;color:var(--text);line-height:1;display:block}
  #speed-unit{font-size:11px;font-weight:600;color:var(--text2);text-transform:uppercase;letter-spacing:1px;margin-top:2px}
  #speedo.speeding #speed-val{color:var(--danger)}

  /* DATA BADGE */
  #data-badge{
    position:absolute;bottom:32px;right:20px;z-index:1000;
    background:var(--surface);backdrop-filter:var(--blur);
    border:1px solid var(--border);border-radius:14px;
    padding:10px 16px;display:flex;gap:16px;
    box-shadow:var(--shadow);
  }
  .badge-item{text-align:center}
  .badge-num{font-size:18px;font-weight:800;color:var(--text);display:block}
  .badge-lbl{font-size:10px;font-weight:600;color:var(--text2);text-transform:uppercase;letter-spacing:.8px}

  /* MAP TOGGLE BTN */
  #btn-map-mode{font-size:18px}

  /* CLUSTER */
  .marker-cluster-small,.marker-cluster-medium,.marker-cluster-large{background:rgba(0,122,255,.15)!important}
  .marker-cluster-small div,.marker-cluster-medium div,.marker-cluster-large div{background:var(--accent)!important;color:#fff!important;font-family:var(--font)!important;font-weight:700!important;font-size:13px!important}

  /* LEAFLET */
  .leaflet-popup-content-wrapper{background:var(--surface2);border:1px solid var(--border);border-radius:var(--r);color:var(--text);backdrop-filter:var(--blur);box-shadow:var(--shadow);font-family:var(--font)}
  .leaflet-popup-tip{background:var(--surface2)}
  .leaflet-control-attribution{background:var(--surface)!important;color:var(--text2)!important;border-radius:8px 0 0 0!important;font-size:10px!important}

  /* Ligne de proximité animée */
  @keyframes dashMove{to{stroke-dashoffset:-34}}
  .leaflet-overlay-pane svg path.prox-animated{animation:dashMove 1s linear infinite}

  /* ═══ MODE TABLEAU DE BORD ═══ */
  #dashboard{
    position:fixed;inset:0;z-index:5000;display:none;
    background:#0a0a0c;flex-direction:column;
    font-family:var(--font);
    /* Empêche le sleep écran via pointer-events trick */
  }
  #dashboard.active{display:flex}

  /* Barre haut : heure + visibilité */
  #db-topbar{
    display:flex;align-items:center;justify-content:space-between;
    padding:14px 24px 0;flex-shrink:0;
  }
  #db-time{font-size:15px;font-weight:700;color:rgba(255,255,255,.45);letter-spacing:.5px}
  #db-vis-pill{
    display:flex;align-items:center;gap:7px;
    background:rgba(255,255,255,.07);border-radius:100px;
    padding:5px 12px;
  }
  #db-vis-dot{width:9px;height:9px;border-radius:50%;background:#34c759;box-shadow:0 0 6px #34c759;transition:.3s}
  #db-vis-dot.orange{background:#ff9500;box-shadow:0 0 6px #ff9500}
  #db-vis-dot.red{background:#ff3b30;box-shadow:0 0 10px #ff3b30;animation:blink .5s infinite alternate}
  #db-vis-lbl{font-size:12px;font-weight:600;color:rgba(255,255,255,.6)}

  /* Zone centrale : compteur vitesse */
  #db-center{
    flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;
    gap:0;position:relative;
  }

  /* Arc de vitesse SVG */
  #db-arc-wrap{position:relative;width:260px;height:160px;flex-shrink:0}
  #db-arc-wrap svg{position:absolute;top:0;left:0}
  #db-arc-bg{stroke:#1e1e22;stroke-width:14;fill:none;stroke-linecap:round}
  #db-arc-fill{stroke:#007aff;stroke-width:14;fill:none;stroke-linecap:round;transition:stroke-dashoffset .4s cubic-bezier(.4,0,.2,1),stroke .3s}
  #db-speed-big{
    position:absolute;bottom:0;left:50%;transform:translateX(-50%);
    text-align:center;
  }
  #db-speed-num{
    font-size:88px;font-weight:800;color:#fff;line-height:.9;display:block;
    transition:color .3s;letter-spacing:-4px;
  }
  #db-speed-unit{font-size:13px;font-weight:600;color:rgba(255,255,255,.35);text-transform:uppercase;letter-spacing:2px}

  /* Carte prochain radar */
  #db-radar-card{
    width:calc(100% - 48px);max-width:400px;
    background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.08);
    border-radius:20px;padding:16px 20px;
    display:flex;align-items:center;gap:16px;
    margin-top:8px;flex-shrink:0;
    transition:background .3s,border-color .3s;
  }
  #db-radar-card.danger{background:rgba(255,59,48,.12);border-color:rgba(255,59,48,.3)}
  #db-radar-card.warn{background:rgba(255,149,0,.1);border-color:rgba(255,149,0,.3)}
  #db-radar-icon-wrap{
    width:48px;height:48px;border-radius:14px;
    background:rgba(255,255,255,.08);
    display:flex;align-items:center;justify-content:center;
    flex-shrink:0;font-size:22px;
  }
  #db-radar-info{flex:1;min-width:0}
  #db-radar-type{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:1.2px;color:rgba(255,255,255,.4);margin-bottom:3px}
  #db-radar-dist{font-size:26px;font-weight:800;color:#fff;line-height:1}
  #db-radar-limit{font-size:12px;color:rgba(255,255,255,.4);margin-top:3px}
  #db-radar-bar-wrap{width:100%;height:4px;background:rgba(255,255,255,.1);border-radius:2px;margin-top:10px;overflow:hidden}
  #db-radar-bar{height:100%;border-radius:2px;background:#34c759;width:0%;transition:width .4s,background .3s}

  /* Barre bas : bouton retour + keepawake */
  #db-bottombar{
    display:flex;align-items:center;justify-content:center;
    padding:0 24px 28px;flex-shrink:0;
  }
  #db-back-btn{
    padding:12px 32px;border-radius:100px;border:1px solid rgba(255,255,255,.12);
    background:rgba(255,255,255,.07);color:rgba(255,255,255,.6);
    font-family:var(--font);font-size:14px;font-weight:600;cursor:pointer;
    transition:.2s;display:flex;align-items:center;gap:8px;
  }
  #db-back-btn:active{background:rgba(255,255,255,.13)}

  /* Fond pulsé quand danger */
  #dashboard.flash-red{animation:flashBg .4s ease}
  @keyframes flashBg{0%{background:#0a0a0c}50%{background:rgba(255,59,48,.08)}100%{background:#0a0a0c}}

  @media(max-width:480px){
    #db-speed-num{font-size:72px}
    #db-arc-wrap{width:220px;height:140px}
    #db-radar-card{padding:12px 16px}
    #fab-group{right:10px}
    #settings-drawer{right:64px;width:210px}
    #speedo{bottom:20px;left:12px}
    #data-badge{bottom:20px;right:12px}
  }
</style>
</head>
<body>

<div id="status-pill"><div id="vis-dot"></div><span id="vis-label">Surveillance active</span></div>

<!-- Overlay géolocalisation -->
<div id="geo-overlay" style="display:none;position:fixed;inset:0;z-index:9999;background:rgba(0,0,0,.7);backdrop-filter:blur(12px);flex-direction:column;align-items:center;justify-content:center;gap:20px;">
  <div style="background:var(--surface2);border:1px solid var(--border);border-radius:24px;padding:32px 28px;text-align:center;max-width:300px;box-shadow:0 16px 48px rgba(0,0,0,.5);">
    <div style="font-size:48px;margin-bottom:16px;">📍</div>
    <div style="font-size:18px;font-weight:800;color:var(--text);margin-bottom:8px;">Localisation requise</div>
    <div style="font-size:13px;color:var(--text2);line-height:1.5;margin-bottom:24px;">RadatBot a besoin de votre position pour afficher les radars et caméras autour de vous. Aucune donnée n'est envoyée à un serveur.</div>
    <button onclick="startTracking()" style="width:100%;padding:14px;border-radius:12px;border:none;background:var(--accent);color:#fff;font-family:var(--font);font-size:15px;font-weight:700;cursor:pointer;">Activer la localisation</button>
    <button onclick="document.getElementById('geo-overlay').style.display='none'" style="width:100%;padding:10px;border-radius:12px;border:none;background:transparent;color:var(--text2);font-family:var(--font);font-size:13px;cursor:pointer;margin-top:8px;">Continuer sans GPS</button>
  </div>
</div>

<div id="alert-banner">
  <div id="alert-type">RADAR</div>
  <div id="alert-dist">—</div>
  <div id="alert-speed"></div>
</div>

<div id="fab-group">
  <div class="fab active" id="fab-locate" onclick="toggleFollow()" title="Centrer">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><line x1="12" y1="2" x2="12" y2="5"/><line x1="12" y1="19" x2="12" y2="22"/><line x1="2" y1="12" x2="5" y2="12"/><line x1="19" y1="12" x2="22" y2="12"/><circle cx="12" cy="12" r="8" stroke-opacity=".25"/></svg>
  </div>
  <div class="fab" id="btn-map-mode" onclick="toggleMapMode()" title="Jour / Nuit">🌙</div>
  <div class="fab" id="fab-dashboard" onclick="enterDashboard()" title="Mode conduite">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="7" width="20" height="14" rx="2"/><path d="M16 3l-4 4-4-4"/><circle cx="8.5" cy="14" r="1.5" fill="currentColor" stroke="none"/><path d="M11.5 14h4"/><path d="M11.5 17h4"/></svg>
  </div>
  <div class="fab" id="fab-settings" onclick="toggleSettings()">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
  </div>
  <div class="fab" onclick="toggleFullscreen()">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"/></svg>
  </div>
</div>

<div id="settings-drawer">
  <div class="drawer-title">Affichage</div>
  <div class="setting-row">
    <div><div class="setting-label">🚨 Radars</div><div class="setting-sub" id="radar-count">—</div></div>
    <label class="toggle"><input type="checkbox" id="tog-radars" checked onchange="toggleLayer('radars',this.checked)"><div class="toggle-track"></div><div class="toggle-thumb"></div></label>
  </div>
  <div class="setting-row">
    <div><div class="setting-label">📷 Caméras</div><div class="setting-sub" id="cam-count">—</div></div>
    <label class="toggle"><input type="checkbox" id="tog-cams" checked onchange="toggleLayer('cameras',this.checked)"><div class="toggle-track"></div><div class="toggle-thumb"></div></label>
  </div>
  <div class="setting-row">
    <div><div class="setting-label">🔊 Alertes audio</div></div>
    <label class="toggle"><input type="checkbox" id="tog-audio" checked><div class="toggle-track"></div><div class="toggle-thumb"></div></label>
  </div>
  <div class="divider"></div>
  <div class="drawer-title">Distance d'alerte</div>
  <div class="thresh-display">
    <div class="thresh-top">
      <span class="setting-label">Seuil</span>
      <span class="setting-label" id="thresh-val" style="color:var(--accent);font-size:15px;font-weight:800">500 m</span>
    </div>
    <input type="range" min="100" max="3000" step="100" value="500" id="thresh-slider" oninput="updateThresh(this.value)">
    <div class="thresh-badges">
      <span class="thresh-badge" onclick="setThresh(200)">200 m</span>
      <span class="thresh-badge sel" onclick="setThresh(500)">500 m</span>
      <span class="thresh-badge" onclick="setThresh(1000)">1 km</span>
      <span class="thresh-badge" onclick="setThresh(2000)">2 km</span>
      <span class="thresh-badge" onclick="setThresh(3000)">3 km</span>
    </div>
  </div>
  <div class="divider"></div>
  <div class="drawer-title">Zoom du suivi GPS</div>
  <div class="thresh-display">
    <div class="thresh-top">
      <span class="setting-label">Niveau</span>
      <span class="setting-label" id="zoom-val" style="color:var(--accent);font-size:15px;font-weight:800">Zoom 15</span>
    </div>
    <input type="range" min="12" max="19" step="1" value="15" id="zoom-slider" oninput="updateFollowZoom(this.value)">
    <div class="thresh-badges">
      <span class="zoom-badge thresh-badge" data-z="12" onclick="updateFollowZoom(12)">🌍 Très large</span>
      <span class="zoom-badge thresh-badge" data-z="14" onclick="updateFollowZoom(14)">🏙️ Ville</span>
      <span class="zoom-badge thresh-badge sel" data-z="15" onclick="updateFollowZoom(15)">🏘️ Quartier</span>
      <span class="zoom-badge thresh-badge" data-z="17" onclick="updateFollowZoom(17)">🛣️ Rue</span>
      <span class="zoom-badge thresh-badge" data-z="19" onclick="updateFollowZoom(19)">🔍 Max</span>
    </div>
  </div>
  <div class="divider"></div>
  <button class="action-btn btn-primary" onclick="testBeep()">🔊 Tester le son</button>
  <button class="action-btn btn-secondary" id="btn-test-line" onclick="toggleTestLine()">📍 Tester ligne radar</button>
  <div class="divider"></div>
  <div class="drawer-title">Mises à jour</div>
  <div id="status-panel">
    <div class="status-row"><span class="status-key">État</span><span class="status-val" id="st-running">—</span></div>
    <div class="status-row"><span class="status-key">Dernière MAJ</span><span class="status-val" id="st-last">—</span></div>
    <div class="status-row"><span class="status-key">Prochaine MAJ</span><span class="status-val" id="st-next">—</span></div>
    <div class="status-row"><span class="status-key">Radars</span><span class="status-val" id="st-radars">—</span></div>
    <div class="status-row"><span class="status-key">Caméras</span><span class="status-val" id="st-cams">—</span></div>
    <div id="st-errors-wrap" style="display:none">
      <div class="status-key" style="font-size:11px;margin-bottom:4px">⚠️ Erreurs récentes</div>
      <div id="error-list"></div>
    </div>
  </div>
  <button class="action-btn btn-force" id="btn-force-update" onclick="forceUpdate()">🔄 Forcer la mise à jour</button>
</div>

<div id="speedo"><span id="speed-val">0</span><span id="speed-unit">km/h</span></div>
<div id="data-badge">
  <div class="badge-item"><span class="badge-num" id="badge-radars">—</span><span class="badge-lbl">Radars</span></div>
  <div class="badge-item"><span class="badge-num" id="badge-cams">—</span><span class="badge-lbl">Caméras</span></div>
</div>

<!-- ═══ MODE TABLEAU DE BORD ═══ -->
<div id="dashboard">
  <!-- Barre supérieure -->
  <div id="db-topbar">
    <span id="db-time">00:00</span>
    <div id="db-vis-pill">
      <div id="db-vis-dot"></div>
      <span id="db-vis-lbl">Hors champ</span>
    </div>
  </div>

  <!-- Centre : arc + vitesse -->
  <div id="db-center">
    <div id="db-arc-wrap">
      <svg width="260" height="160" viewBox="0 0 260 160">
        <!-- Arc de fond -->
        <path id="db-arc-bg" d="M30,150 A110,110 0 0,1 230,150" stroke-width="14" stroke="#1e1e22" fill="none" stroke-linecap="round"/>
        <!-- Arc de vitesse -->
        <path id="db-arc-fill" d="M30,150 A110,110 0 0,1 230,150" stroke-width="14" stroke="#007aff" fill="none" stroke-linecap="round"
          style="stroke-dasharray:345;stroke-dashoffset:345;transition:stroke-dashoffset .45s cubic-bezier(.4,0,.2,1),stroke .3s"/>
        <!-- Marqueurs de vitesse -->
        <text x="24" y="158" font-family="Outfit,sans-serif" font-size="10" fill="rgba(255,255,255,.3)" text-anchor="middle">0</text>
        <text x="130" y="38" font-family="Outfit,sans-serif" font-size="10" fill="rgba(255,255,255,.3)" text-anchor="middle">80</text>
        <text x="236" y="158" font-family="Outfit,sans-serif" font-size="10" fill="rgba(255,255,255,.3)" text-anchor="middle">160</text>
      </svg>
      <div id="db-speed-big">
        <span id="db-speed-num">0</span>
        <span id="db-speed-unit">km/h</span>
      </div>
    </div>

    <!-- Carte prochain radar -->
    <div id="db-radar-card">
      <div id="db-radar-icon-wrap">🚨</div>
      <div id="db-radar-info">
        <div id="db-radar-type">Prochain capteur</div>
        <div id="db-radar-dist">—</div>
        <div id="db-radar-limit"></div>
        <div id="db-radar-bar-wrap"><div id="db-radar-bar"></div></div>
      </div>
    </div>
  </div>

  <!-- Barre inférieure -->
  <div id="db-bottombar">
    <button id="db-back-btn" onclick="exitDashboard()">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="M19 12H5"/><path d="M12 5l-7 7 7 7"/></svg>
      Retour à la carte
    </button>
  </div>
</div>

<div id="map"></div>

<script>
// ─── TILES ───
const TILES = {
  day: {
    url: 'https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png',
    attr: '© CartoDB © OSM'
  },
  night: {
    url: 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
    attr: '© CartoDB © OSM'
  }
};

// Auto-detect day/night by hour
function isNight() {
  const h = new Date().getHours();
  return h < 7 || h >= 20;
}

let darkMode = isNight();
let tileLayer;

let map, userMarker, accuracyCircle, proximityLine, proximityLineBg, proximityLineGlow;
let radarCluster = L.markerClusterGroup({disableClusteringAtZoom:15,maxClusterRadius:60,animate:false,chunkedLoading:true});
let cameraCluster = L.markerClusterGroup({disableClusteringAtZoom:15,maxClusterRadius:50,animate:false,chunkedLoading:true});
let allRadars=[], allCameras=[], allTroncons=[];
let following=true, testLine=false;
let followZoom=15;
let lastPos={lat:48.8566,lng:2.3522,heading:0};
let alertedSet=new Set(), alertThreshold=500;
let audioCtx=null;

function applyTheme(){
  document.body.classList.toggle('dark', darkMode);
  document.getElementById('btn-map-mode').textContent = darkMode ? '☀️' : '🌙';
  if(tileLayer) map.removeLayer(tileLayer);
  tileLayer = L.tileLayer(darkMode ? TILES.night.url : TILES.day.url, {
    attribution: TILES.day.attr, maxZoom:20, keepBuffer:2, updateWhenIdle:true
  }).addTo(map);
  tileLayer.bringToBack();
}

function toggleMapMode(){
  darkMode = !darkMode;
  applyTheme();
}

function initMap(){
  map = L.map('map',{
    zoomControl:false,preferCanvas:true,updateWhenZooming:false,updateWhenIdle:true,
    tap:false,tapTolerance:15,bounceAtZoomLimits:false,
    dragging:true,touchZoom:true,scrollWheelZoom:true,doubleClickZoom:true,boxZoom:false
  }).setView([48.8566,2.3522],13);

  applyTheme();
  map.addLayer(radarCluster);
  map.addLayer(cameraCluster);

  proximityLineBg   = L.polyline([],{color:'rgba(255,59,48,.18)',weight:10,lineCap:'round',lineJoin:'round'}).addTo(map);
  proximityLineGlow = L.polyline([],{color:'rgba(255,59,48,.35)',weight:6,lineCap:'round',lineJoin:'round'}).addTo(map);
  proximityLine     = L.polyline([],{color:'#ff3b30',weight:2.5,dashArray:'10 7',opacity:.95,lineCap:'round'}).addTo(map);
  setTimeout(()=>{
    const el=proximityLine.getElement && proximityLine.getElement();
    if(el) el.classList.add('prox-animated');
  },300);

  map.on('dragstart',()=>{ following=false; document.getElementById('fab-locate').classList.remove('active'); });
  // Quand l'utilisateur zoome manuellement, on mémorise le nouveau zoom pour le suivi
  map.on('zoomend',()=>{
    if(following){
      followZoom=map.getZoom();
      // Sync slider et badges sans déclencher setView
      document.getElementById('zoom-val').textContent='Zoom '+followZoom;
      if(document.getElementById('zoom-slider')) document.getElementById('zoom-slider').value=followZoom;
      document.querySelectorAll('.zoom-badge').forEach(b=>b.classList.toggle('sel',parseInt(b.dataset.z)===followZoom));
    }
  });
  map.on('click',()=>document.getElementById('settings-drawer').classList.remove('open'));

  loadRadars(); loadCameras();
  promptGeoloc();
}

// Demande de géolocalisation avec overlay propre
function promptGeoloc(){
  if(!navigator.geolocation){ return; }
  // Vérifie si permission déjà accordée
  if(navigator.permissions){
    navigator.permissions.query({name:'geolocation'}).then(r=>{
      if(r.state==='granted'){ startTracking(); }
      else { showGeoOverlay(); }
    }).catch(()=>showGeoOverlay());
  } else {
    showGeoOverlay();
  }
}

function showGeoOverlay(){
  document.getElementById('geo-overlay').style.display='flex';
}

function startTracking(){
  document.getElementById('geo-overlay').style.display='none';
  navigator.geolocation.watchPosition(onPosition, err=>{
    console.warn('GPS:',err.message);
    if(err.code===1) showGeoOverlay(); // permission refusée
  }, {enableHighAccuracy:true,maximumAge:0,timeout:10000});
}

// ─── POSITION ───
let _lastVisibilityCheck=0;
function onPosition(pos){
  const {latitude:lat,longitude:lng,speed,heading,accuracy}=pos.coords;
  const kmh=Math.round((speed||0)*3.6);
  const hdg=heading||lastPos.heading;
  lastPos={lat,lng,heading:hdg};
  document.getElementById('speed-val').textContent=kmh;
  document.getElementById('speedo').classList.toggle('speeding',kmh>130);
  updateUserMarker(lat,lng,hdg,accuracy);
  // computeVisibility est coûteux avec 70k caméras → max toutes les 3s
  const now=Date.now();
  if(now-_lastVisibilityCheck>3000){
    computeVisibility(lat,lng,hdg,kmh);
    _lastVisibilityCheck=now;
  }
  updateAlerts(lat,lng);
  if(following) map.setView([lat,lng], followZoom, {animate:true,duration:0.5});
  if(dashActive){ updateDashSpeed(kmh); updateDashRadar(lat,lng); }
}

function updateUserMarker(lat,lng,hdg,acc){
  const fill = darkMode ? '#0a84ff' : '#007aff';
  const ring = darkMode ? 'rgba(10,132,255,.2)' : 'rgba(0,122,255,.15)';
  const icon=L.divIcon({
    className:'',
    html:`<svg width="44" height="44" viewBox="0 0 44 44" xmlns="http://www.w3.org/2000/svg" style="transform:rotate(${hdg||0}deg)">
      <circle cx="22" cy="22" r="20" fill="${ring}" stroke="${fill}" stroke-width="2.5"/>
      <circle cx="22" cy="22" r="5" fill="${fill}"/>
      <path d="M22 5 L29 33 L22 27 L15 33 Z" fill="${fill}"/>
    </svg>`,
    iconSize:[44,44], iconAnchor:[22,22]
  });
  if(!userMarker){
    userMarker=L.marker([lat,lng],{icon,zIndexOffset:9999}).addTo(map);
    accuracyCircle=L.circle([lat,lng],{radius:acc||20,color:fill,weight:1,fillOpacity:.06}).addTo(map);
  } else {
    userMarker.setLatLng([lat,lng]); userMarker.setIcon(icon);
    accuracyCircle.setLatLng([lat,lng]).setRadius(acc||20);
  }
}

// ─── VISIBILITY ENGINE ───
// But : détecter si un capteur peut NOUS VOIR / nous identifier, pas si on l'approche.
//
// Modèle physique :
//  CAMÉRA (dôme/LAPI/fixe) : omnidirectionnelle par défaut (360°).
//    → Le seul facteur est la distance. Une caméra derrière nous peut très bien nous voir.
//    → Portée utile : 80m (lecture plaque nette), 200m (présence détectable)
//    → Score = fonction exponentielle décroissante de la distance
//
//  RADAR FIXE / TRONÇON : bidirectionnel ou unidirectionnel, mais sans info de cap
//    → On traite comme omnidirectionnel à courte portée avec score distance
//    → Portée : 150m (fixe), 500m (tronçon)
//
//  RADAR MOBILE : directionnel, on modèle un cône depuis le capteur vers nous
//    → Angle : depuis le capteur on calcule si on est "devant" lui
//    → Approximation : si on s'approche du capteur (distance décroit), risque max
//
//  Score final [0..1] → seuils 0.25=orange, 0.6=rouge

function bearingTo(fromLat,fromLng,toLat,toLng){
  const dLon=(toLng-fromLng)*Math.PI/180;
  const lat1=fromLat*Math.PI/180, lat2=toLat*Math.PI/180;
  const y=Math.sin(dLon)*Math.cos(lat2);
  const x=Math.cos(lat1)*Math.sin(lat2)-Math.sin(lat1)*Math.cos(lat2)*Math.cos(dLon);
  return (Math.atan2(y,x)*180/Math.PI+360)%360;
}
function angleDiff(a,b){ return Math.abs((a-b+180+360)%360-180); }

// Courbe douce : score=1 à d=0, score=0 à d=range, décroissance exponentielle
function distScore(d, range, steepness=3){
  return Math.max(0, Math.exp(-steepness*(d/range)));
}

function computeVisibility(lat,lng,hdg,speedKmh){
  let maxScore=0;

  // ── CAMÉRAS : omnidirectionnelles ──
  // Portée réelle lecture plaque : ~50m net, ~100m détectable
  // Avec 70k caméras on reste strict sur la distance
  for(const c of allCameras){
    if(!c.latitude||!c.longitude) continue;
    const d=map.distance([lat,lng],[c.latitude,c.longitude]);
    if(d>120) continue;
    // Score exponentiel : à 40m = élevé, à 100m = faible
    const score=distScore(d, 100, 5);
    if(score>maxScore) maxScore=score;
    if(maxScore>=0.95) break;
  }

  // ── RADARS ──
  for(const r of allRadars){
    if(!r.lat||!r.lng) continue;
    const d=map.distance([lat,lng],[r.lat,r.lng]);
    const cls=classifyRadar(r.type||'');
    let range=150, steep=3.5, directional=false;

    if(cls==='troncon'){range=500;steep=2;}
    else if(cls==='mobile'){range=120;steep=4;directional=true;}
    else if(cls==='feu'){range=80;steep=5;}
    else if(cls==='pesage'){range=100;steep=4;}

    if(d>range) continue;

    let score=distScore(d, range, steep);

    // Radar mobile : directionnel → score réduit si on n'est pas dans son axe de mesure.
    // On modèle que le radar mobile fait face à une direction ≈ la notre + 180°
    // (il nous mesure de face ou de dos). Si on est de côté = score réduit.
    if(directional){
      // Cap depuis le radar vers nous
      const brgFromRadar=bearingTo(r.lat,r.lng,lat,lng);
      // On suppose que le radar est aligné sur la route = notre cap ou son opposé
      const frontAngle=angleDiff(brgFromRadar, hdg);         // face à face
      const rearAngle =angleDiff(brgFromRadar, (hdg+180)%360); // dos à dos
      const axisAngle =Math.min(frontAngle, rearAngle);      // plus proche des deux axes
      // Dans l'axe (<30°) = plein score, de côté (>60°) = score réduit de 70%
      const dirFactor = axisAngle<30 ? 1 : axisAngle<60 ? 0.6 : 0.25;
      score*=dirFactor;
    }

    // Facteur vitesse pour les radars vitesse
    if(cls==='fixe'||cls==='troncon'||cls==='mobile'){
      if(speedKmh>130) score=Math.min(1,score*1.5);
      else if(speedKmh>90) score=Math.min(1,score*1.2);
    }

    if(score>maxScore) maxScore=score;
  }

  // Mise à jour du dot
  const dot=document.getElementById('vis-dot');
  const lbl=document.getElementById('vis-label');
  dot.className='';
  if(maxScore>=0.75){
    dot.classList.add('red'); lbl.textContent='Zone de capture';
  } else if(maxScore>=0.45){
    dot.classList.add('orange'); lbl.textContent='Capteur en portée';
  } else {
    lbl.textContent='Hors champ';
  }
  // Sync dashboard dot
  if(dashActive) updateDashVis();
}

// ─── ALERTS ───
function updateAlerts(lat,lng){
  let minDist=Infinity, closest=null, closestType='RADAR';
  for(const r of allRadars){
    if(!r.lat||!r.lng) continue;
    const d=map.distance([lat,lng],[r.lat,r.lng]);
    if(d<minDist){minDist=d;closest=r;closestType=getRadarLabel(r.type||'');}
  }
  const banner=document.getElementById('alert-banner');
  const thresh=testLine?99999:alertThreshold;
  if(closest&&minDist<thresh){
    const ll=[[lat,lng],[closest.lat,closest.lng]];
    proximityLineBg.setLatLngs(ll);
    proximityLineGlow.setLatLngs(ll);
    proximityLine.setLatLngs(ll);
    document.getElementById('alert-type').textContent=closestType;
    document.getElementById('alert-dist').textContent=minDist<1000?Math.round(minDist)+' m':(minDist/1000).toFixed(1)+' km';
    document.getElementById('alert-speed').textContent=closest.vitesse?'Limite : '+closest.vitesse+' km/h':'';
    banner.classList.add('show');
    for(const step of [alertThreshold,700,500,400,300,200,100,30]){
      if(minDist<=step&&!alertedSet.has(step)){
        if(document.getElementById('tog-audio').checked) playBeep(step<200?1050:880,step<100?.5:.25);
        alertedSet.add(step);
      }
    }
  } else {
    proximityLine.setLatLngs([]);
    proximityLineBg.setLatLngs([]);
    proximityLineGlow.setLatLngs([]);
    banner.classList.remove('show');
  }
  if(minDist>alertThreshold+150) alertedSet.clear();
}

// ─── LOAD DATA ───
async function loadRadars(){
  try{
    const r=await fetch('/api/radars'); const data=await r.json();
    // Support nouveau format {radars, troncons} ET ancien format tableau
    allRadars = Array.isArray(data) ? data : (data.radars || []);
    allTroncons = Array.isArray(data) ? [] : (data.troncons || []);

    document.getElementById('badge-radars').textContent=allRadars.length;
    document.getElementById('radar-count').textContent=allRadars.length+' entrées';
    const layers=[];
    allRadars.forEach(rd=>{
      if(!rd.lat||!rd.lng) return;
      const m=L.marker([rd.lat,rd.lng],{icon:getRadarIcon(rd.type||'',rd.vitesse)});
      m.bindPopup(`<b>${getRadarLabel(rd.type||'')}</b>${rd.vitesse?'<br>Limite : '+rd.vitesse+' km/h':''}${rd.route?'<br>'+rd.route:''}${rd.commune?'<br>'+rd.commune:''}`,{maxWidth:200});
      layers.push(m);
    });
    radarCluster.addLayers(layers);

    // Pas de tracé tronçon — les radars tronçons sont affichés comme marqueurs normaux
  } catch(e){console.error('Radars:',e);}
}

async function loadCameras(){
  try{
    const r=await fetch('/api/cameras'); allCameras=await r.json();
    document.getElementById('badge-cams').textContent=allCameras.length;
    document.getElementById('cam-count').textContent=allCameras.length+' entrées';
    const layers=[];
    allCameras.forEach(c=>{
      if(!c.latitude||!c.longitude) return;
      const isKML = c.source === 'KML-Paris';
      const isMarseille = c.source === 'uMap-Marseille';
      const icon = makeCameraIconOSM();
      const m=L.marker([c.latitude,c.longitude],{icon});
      const srcLabel = isKML ? '🔵 Préfecture Paris' : isMarseille ? '🔵 uMap Marseille' : '🔵 OpenStreetMap';
      m.bindPopup(`<b>${c.nom||'Caméra'}</b><br><small>${srcLabel}</small>${c.direction&&c.direction!=='Non spécifiée'?'<br>'+c.direction:''}`,{maxWidth:220});
      layers.push(m);
    });
    cameraCluster.addLayers(layers);
  } catch(e){console.error('Cameras:',e);}
}

// Caméra OSM — bleu
function makeCameraIconOSM(){
  const svg=`<svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
    <path d="M23 7l-7 5 7 5V7z" fill="#fff" opacity=".9"/>
    <rect x="1" y="5" width="15" height="14" rx="2.5" fill="#fff" opacity=".9"/>
    <circle cx="8.5" cy="12" r="3.5" fill="#007aff"/>
    <circle cx="8.5" cy="12" r="1.5" fill="#fff"/>
  </svg>`;
  return L.divIcon({className:'',html:`<div style="width:34px;height:34px;border-radius:50%;background:#1c3a5e;border:2.5px solid #007aff;display:flex;align-items:center;justify-content:center;box-shadow:0 3px 10px rgba(0,122,255,.35);">${svg}</div>`,iconSize:[34,34],iconAnchor:[17,17]});
}

// Caméra Préfecture Paris — bleu
function makeCameraIconParis(){
  const svg=`<svg width="18" height="18" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
    <path d="M23 7l-7 5 7 5V7z" fill="#fff" opacity=".9"/>
    <rect x="1" y="5" width="15" height="14" rx="2.5" fill="#fff" opacity=".9"/>
    <circle cx="8.5" cy="12" r="3.5" fill="#007aff"/>
    <circle cx="8.5" cy="12" r="1.5" fill="#fff"/>
  </svg>`;
  return L.divIcon({className:'',html:`<div style="width:34px;height:34px;border-radius:50%;background:#1c3a5e;border:2.5px solid #007aff;display:flex;align-items:center;justify-content:center;box-shadow:0 3px 10px rgba(0,122,255,.45);">${svg}</div>`,iconSize:[34,34],iconAnchor:[17,17]});
}

// Classify radar type from API string
function classifyRadar(type){
  const t=(type||'').toLowerCase();
  if(t==='feu_rouge'||t==='feu_vitesse'||t.includes('feu')||t.includes('rouge')) return 'feu';
  if(t==='troncon'||t.includes('troncon')||t.includes('tronçon')||t.includes('section')||t.includes('itineraire')||t.includes('moyenne')) return 'troncon';
  if(t==='voiture'||t.includes('voiture')||t.includes('embarqu')) return 'voiture';
  if(t==='urbain'||t.includes('urbain')) return 'urbain';
  if(t==='mobile'||t.includes('mobile')||t.includes('chantier')||t.includes('autonome')) return 'mobile';
  if(t==='passage_niveau'||t.includes('passage')||t.includes('niveau')) return 'passage_niveau';
  if(t==='tourelle'||t.includes('tourelle')) return 'tourelle';
  if(t==='double_sens'||t==='double_face'||t.includes('double')||t.includes('discriminant')) return 'troncon';
  if(t==='pesage'||t.includes('pesag')) return 'pesage';
  return 'fixe';
}

function getRadarLabel(type){
  const c=classifyRadar(type);
  const labels={
    fixe:'RADAR FIXE', troncon:'RADAR TRONÇON', mobile:'RADAR MOBILE',
    feu:'FEU ROUGE', pesage:'PESAGE', passage_niveau:'PASSAGE À NIVEAU',
    tourelle:'RADAR TOURELLE', urbain:'RADAR URBAIN', voiture:'VOITURE RADAR'
  };
  return labels[c]||'RADAR';
}


// SVG icon builder
function svgIcon(svgInner, bg, border, size=40){
  const html=`<div style="
    width:${size}px;height:${size}px;border-radius:50%;
    background:${bg};border:3px solid ${border};
    display:flex;align-items:center;justify-content:center;
    box-shadow:0 3px 12px rgba(0,0,0,.28);
    ">${svgInner}</div>`;
  return L.divIcon({className:'',html,iconSize:[size,size],iconAnchor:[size/2,size/2]});
}

function getRadarIcon(type, vitesse){
  const c=classifyRadar(type);

  if(c==='feu'){
    // Traffic light icon
    const svg=`<svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect x="7" y="2" width="10" height="20" rx="3" fill="#1c1c1e" stroke="#ff9500" stroke-width="1.5"/>
      <circle cx="12" cy="6" r="2.2" fill="#ff3b30"/>
      <circle cx="12" cy="12" r="2.2" fill="#ff9500"/>
      <circle cx="12" cy="18" r="2.2" fill="#34c759"/>
      <line x1="12" y1="22" x2="12" y2="24" stroke="#ff9500" stroke-width="1.5"/>
    </svg>`;
    return svgIcon(svg,'#1c1c1e','#ff9500',38);
  }

  if(c==='troncon'){
    // Two radar posts connected
    const svg=`<svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect x="3" y="4" width="4" height="12" rx="1.5" fill="#fff" opacity=".9"/>
      <rect x="17" y="4" width="4" height="12" rx="1.5" fill="#fff" opacity=".9"/>
      <path d="M7 7 Q12 4 17 7" stroke="#fff" stroke-width="1.8" fill="none" stroke-linecap="round"/>
      <path d="M7 11 Q12 8 17 11" stroke="#fff" stroke-width="1.2" fill="none" stroke-linecap="round" opacity=".5"/>
      <line x1="5" y1="16" x2="5" y2="20" stroke="#fff" stroke-width="1.5" opacity=".7"/>
      <line x1="19" y1="16" x2="19" y2="20" stroke="#fff" stroke-width="1.5" opacity=".7"/>
    </svg>`;
    return svgIcon(svg,'#5856d6','#7b79e8',40);
  }

  if(c==='mobile'){
    // Pistolet radar / radar mobile — icône pistolet radar réaliste
    const svg=`<svg width="22" height="22" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <!-- Corps du pistolet radar -->
      <rect x="2" y="9" width="13" height="6" rx="2" fill="#fff" opacity=".95"/>
      <!-- Poignée -->
      <rect x="5" y="15" width="4" height="5" rx="1.5" fill="#fff" opacity=".8"/>
      <!-- Canon / objectif -->
      <rect x="14" y="10.5" width="5" height="3" rx="1" fill="#fff" opacity=".9"/>
      <circle cx="20" cy="12" r="1.5" fill="#ff9500"/>
      <!-- Ondes radar -->
      <path d="M20.5 8.5 Q23 10 23 12 Q23 14 20.5 15.5" stroke="#fff" stroke-width="1.4" fill="none" stroke-linecap="round" opacity=".8"/>
      <path d="M21.5 10 Q24 11 24 12 Q24 13 21.5 14" stroke="#fff" stroke-width="1" fill="none" stroke-linecap="round" opacity=".45"/>
      <!-- Gâchette -->
      <path d="M7 15 L6 19" stroke="#fff" stroke-width="1.5" stroke-linecap="round" opacity=".7"/>
    </svg>`;
    return svgIcon(svg,'#b45309','#ff9500',40);
  }

  if(c==='pesage'){
    // Scale/truck
    const svg=`<svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect x="2" y="14" width="20" height="4" rx="1" fill="#fff" opacity=".9"/>
      <line x1="12" y1="6" x2="12" y2="14" stroke="#fff" stroke-width="1.8"/>
      <line x1="6" y1="10" x2="18" y2="10" stroke="#fff" stroke-width="1.8" stroke-linecap="round"/>
      <circle cx="6" cy="10" r="2" fill="#fff" opacity=".9"/>
      <circle cx="18" cy="10" r="2" fill="#fff" opacity=".9"/>
      <circle cx="12" cy="6" r="1.5" fill="#fff"/>
    </svg>`;
    return svgIcon(svg,'#30b0c7','#5ac8fa',38);
  }

  if(c==='urbain'){
    // Radar urbain — caméra sur potelet de ville
    const svg=`<svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <line x1="12" y1="22" x2="12" y2="10" stroke="#fff" stroke-width="2" stroke-linecap="round"/>
      <rect x="8" y="6" width="10" height="7" rx="2" fill="#fff" opacity=".9"/>
      <circle cx="13" cy="9.5" r="2.2" fill="#34c759"/>
      <circle cx="13" cy="9.5" r="1" fill="#1c1c1e"/>
      <rect x="10" y="20" width="4" height="2" rx="1" fill="#fff" opacity=".7"/>
      <rect x="7" y="22" width="10" height="1.5" rx=".75" fill="#fff" opacity=".5"/>
    </svg>`;
    return svgIcon(svg,'#0a7a3c','#34c759',40);
  }

  if(c==='voiture'){
    // Voiture radar embarquée — voiture avec flash
    const svg=`<svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect x="1" y="10" width="18" height="9" rx="2.5" fill="#fff" opacity=".9"/>
      <path d="M3 10 L5 5 H15 L17 10" fill="#fff" opacity=".7"/>
      <circle cx="5" cy="19" r="2.2" fill="#fff"/>
      <circle cx="15" cy="19" r="2.2" fill="#fff"/>
      <rect x="20" y="8" width="3" height="6" rx="1.5" fill="#fff" opacity=".6"/>
      <path d="M20 7 L22 4 L24 7" fill="#fff" opacity=".8" stroke-linejoin="round"/>
      <circle cx="7" cy="8" r="1" fill="#e879f9" opacity=".9"/>
      <circle cx="11" cy="7" r="1" fill="#e879f9" opacity=".9"/>
    </svg>`;
    return svgIcon(svg,'#7c3aed','#e879f9',40);
  }

  if(c==='passage_niveau'){
    const svg=`<svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <line x1="4" y1="4" x2="20" y2="20" stroke="#fff" stroke-width="2.2" stroke-linecap="round"/>
      <line x1="20" y1="4" x2="4" y2="20" stroke="#fff" stroke-width="2.2" stroke-linecap="round"/>
      <circle cx="4" cy="4" r="2" fill="#ff3b30"/>
      <circle cx="20" cy="4" r="2" fill="#ff3b30"/>
    </svg>`;
    return svgIcon(svg,'#1c1c1e','#ff3b30',38);
  }

  // Radar fixe — boîtier radar réaliste
  // Avec vitesse en surimpression si disponible
  const spd=vitesse?`<text x="20" y="35" text-anchor="middle" font-family="Outfit,sans-serif" font-size="8" font-weight="800" fill="#ff3b30">${vitesse}</text>`:'';
  const svgBox=`<svg width="28" height="28" viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
    <!-- Support / mât -->
    <rect x="18" y="26" width="4" height="10" rx="1.5" fill="#888"/>
    <rect x="14" y="34" width="12" height="3" rx="1.5" fill="#666"/>
    <!-- Caisson principal -->
    <rect x="6" y="8" width="28" height="20" rx="4" fill="#2c2c2e" stroke="#444" stroke-width="1.2"/>
    <!-- Vitre / objectif -->
    <rect x="10" y="12" width="20" height="12" rx="2.5" fill="#1a1a2e" stroke="#555" stroke-width=".8"/>
    <!-- Lentille centrale -->
    <circle cx="20" cy="18" r="5" fill="#0a0a1a" stroke="#ff3b30" stroke-width="1.5"/>
    <circle cx="20" cy="18" r="2.5" fill="#1c1c3a"/>
    <circle cx="18.5" cy="16.5" r=".9" fill="rgba(255,255,255,.25)"/>
    <!-- Indicateur LED -->
    <circle cx="29" cy="12" r="1.8" fill="#ff3b30"/>
    <!-- Flash éclair -->
    <path d="M22 14 L19.5 18.5 L21.5 18.5 L19 22 L22.5 17 L20.5 17 Z" fill="#ff9500" opacity=".85"/>
    ${spd}
  </svg>`;
  const label=vitesse?`<span style="position:absolute;bottom:-1px;left:50%;transform:translateX(-50%);font-family:'Outfit',sans-serif;font-size:9px;font-weight:800;color:#ff3b30;white-space:nowrap;line-height:1;">${vitesse}</span>`:'';
  const html=`<div style="position:relative;width:44px;height:44px;border-radius:50%;background:#fff;border:3px solid #ff3b30;display:flex;align-items:center;justify-content:center;box-shadow:0 3px 14px rgba(255,59,48,.45);">${svgBox}${label}</div>`;
  return L.divIcon({className:'',html,iconSize:[44,44],iconAnchor:[22,22]});
}

// Camera icon — lens SVG
// ─── AUDIO ───
function getCtx(){
  if(!audioCtx) audioCtx=new(window.AudioContext||window.webkitAudioContext)();
  if(audioCtx.state==='suspended') audioCtx.resume();
  return audioCtx;
}
function playBeep(freq=880,vol=.25,dur=160){
  try{
    const ctx=getCtx(), osc=ctx.createOscillator(), g=ctx.createGain();
    osc.connect(g); g.connect(ctx.destination);
    osc.frequency.value=freq;
    g.gain.setValueAtTime(vol,ctx.currentTime);
    g.gain.exponentialRampToValueAtTime(.001,ctx.currentTime+dur/1000);
    osc.start(ctx.currentTime); osc.stop(ctx.currentTime+dur/1000);
  }catch(e){}
}
function testBeep(){playBeep(880,.4,200);}

// ─── CONTROLS ───
function toggleFollow(){
  following=!following;
  document.getElementById('fab-locate').classList.toggle('active',following);
  if(following){
    map.setView([lastPos.lat,lastPos.lng], followZoom, {animate:true,duration:0.6});
  }
}
function toggleSettings(){
  document.getElementById('settings-drawer').classList.toggle('open');
  document.getElementById('fab-settings').classList.toggle('active');
}
function toggleLayer(type,on){
  if(type==='radars') on?map.addLayer(radarCluster):map.removeLayer(radarCluster);
  else on?map.addLayer(cameraCluster):map.removeLayer(cameraCluster);
}
function toggleFullscreen(){
  // iOS Safari ne supporte pas requestFullscreen — on utilise un pseudo-fullscreen CSS
  const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent) || (navigator.platform==='MacIntel'&&navigator.maxTouchPoints>1);
  if(isIOS){
    document.body.classList.toggle('ios-fullscreen');
    const btn=document.querySelector('.fab[onclick="toggleFullscreen()"]');
    const isFs=document.body.classList.contains('ios-fullscreen');
    if(btn) btn.innerHTML=isFs
      ?`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M8 3v3a2 2 0 0 1-2 2H3m18 0h-3a2 2 0 0 1-2-2V3m0 18v-3a2 2 0 0 0 2-2h3M3 16h3a2 2 0 0 0 2 2v3"/></svg>`
      :`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"/></svg>`;
    return;
  }
  if(!document.fullscreenElement){
    document.documentElement.requestFullscreen().catch(()=>{
      // Fallback si refusé
      document.body.classList.add('ios-fullscreen');
    });
  } else {
    document.exitFullscreen().catch(()=>{});
  }
}
function updateThresh(v){
  alertThreshold=parseInt(v);
  const label = v>=1000 ? (v/1000).toFixed(v%1000===0?0:1)+' km' : v+' m';
  document.getElementById('thresh-val').textContent=label;
  document.getElementById('thresh-slider').value=v;
  // Sync badges
  document.querySelectorAll('.thresh-badge').forEach(b=>{
    b.classList.toggle('sel', parseInt(b.textContent)===alertThreshold||b.textContent===label);
  });
  alertedSet.clear();
}
function setThresh(v){
  updateThresh(v);
}
function updateFollowZoom(v){
  followZoom=parseInt(v);
  document.getElementById('zoom-val').textContent='Zoom '+v;
  document.getElementById('zoom-slider').value=v;
  document.querySelectorAll('.zoom-badge').forEach(b=>{
    b.classList.toggle('sel', parseInt(b.dataset.z)===followZoom);
  });
  // Appliquer immédiatement si suivi actif
  if(following) map.setView([lastPos.lat,lastPos.lng], followZoom, {animate:true,duration:0.5});
}
function toggleTestLine(){
  testLine=!testLine;
  const btn=document.getElementById('btn-test-line');
  btn.className='action-btn '+(testLine?'btn-danger':'btn-secondary');
  btn.textContent=testLine?'❌ Stopper le test':'📍 Tester ligne radar';
  if(testLine) updateAlerts(lastPos.lat,lastPos.lng);
  else{proximityLine.setLatLngs([]);document.getElementById('alert-banner').classList.remove('show');}
}

// ─── DASHBOARD ───
let dashActive=false, dashClock=null, wakeLock=null;
const ARC_LEN=345;
const DB_MAX_SPEED=160;

function enterDashboard(){
  dashActive=true;
  document.getElementById('dashboard').classList.add('active');
  document.getElementById('fab-group').style.display='none';
  document.getElementById('speedo').style.display='none';
  document.getElementById('data-badge').style.display='none';
  document.getElementById('status-pill').style.display='none';
  document.getElementById('alert-banner').classList.remove('show');
  if(!document.fullscreenElement) document.documentElement.requestFullscreen().catch(()=>{});
  if('wakeLock' in navigator) navigator.wakeLock.request('screen').then(wl=>wakeLock=wl).catch(()=>{});
  dashClock=setInterval(updateDashClock,1000);
  updateDashClock();
}

function exitDashboard(){
  dashActive=false;
  document.getElementById('dashboard').classList.remove('active');
  document.getElementById('fab-group').style.display='flex';
  document.getElementById('speedo').style.display='block';
  document.getElementById('data-badge').style.display='flex';
  document.getElementById('status-pill').style.display='flex';
  if(document.fullscreenElement) document.exitFullscreen().catch(()=>{});
  if(wakeLock){ wakeLock.release(); wakeLock=null; }
  clearInterval(dashClock); dashClock=null;
}

function updateDashClock(){
  const n=new Date();
  document.getElementById('db-time').textContent=
    String(n.getHours()).padStart(2,'0')+':'+String(n.getMinutes()).padStart(2,'0');
}

function updateDashSpeed(kmh){
  const ratio=Math.min(kmh/DB_MAX_SPEED,1);
  document.getElementById('db-arc-fill').style.strokeDashoffset=ARC_LEN-(ARC_LEN*ratio);
  document.getElementById('db-arc-fill').style.stroke=kmh>120?'#ff3b30':kmh>90?'#ff9500':'#007aff';
  const n=document.getElementById('db-speed-num');
  n.textContent=kmh;
  n.style.color=kmh>120?'#ff3b30':kmh>90?'#ff9500':'#fff';
}

function updateDashRadar(lat,lng){
  let minDist=Infinity, closest=null;
  for(const r of allRadars){
    if(!r.lat||!r.lng) continue;
    const d=map.distance([lat,lng],[r.lat,r.lng]);
    if(d<minDist){minDist=d;closest=r;}
  }
  for(const c of allCameras){
    if(!c.latitude||!c.longitude) continue;
    const d=map.distance([lat,lng],[c.latitude,c.longitude]);
    if(d<minDist){minDist=d;closest={...c,lat:c.latitude,lng:c.longitude,_isCam:true};}
  }

  const card=document.getElementById('db-radar-card');
  const distEl=document.getElementById('db-radar-dist');
  const typeEl=document.getElementById('db-radar-type');
  const limitEl=document.getElementById('db-radar-limit');
  const barEl=document.getElementById('db-radar-bar');
  const iconEl=document.getElementById('db-radar-icon-wrap');

  if(closest){
    distEl.textContent=minDist<1000?Math.round(minDist)+' m':(minDist/1000).toFixed(1)+' km';
    if(closest._isCam){
      typeEl.textContent='Caméra de surveillance'; iconEl.textContent='📷'; limitEl.textContent='';
    } else {
      typeEl.textContent=getRadarLabel(closest.type||'');
      iconEl.textContent=closest.type?.includes('feu')?'🚦':'🚨';
      limitEl.textContent=closest.vitesse?'Limite : '+closest.vitesse+' km/h':'';
    }
    const barPct=Math.max(0,Math.min(100,100-(minDist/alertThreshold)*100));
    barEl.style.width=barPct+'%';
    barEl.style.background=minDist<200?'#ff3b30':minDist<500?'#ff9500':'#34c759';
    card.className=minDist<200?'danger':minDist<alertThreshold?'warn':'';
    if(minDist<100){
      const db=document.getElementById('dashboard');
      db.classList.add('flash-red');
      setTimeout(()=>db.classList.remove('flash-red'),400);
    }
  } else {
    distEl.textContent='—'; typeEl.textContent='Aucun capteur proche';
    limitEl.textContent=''; barEl.style.width='0%'; card.className=''; iconEl.textContent='✅';
  }
}

function updateDashVis(){
  const dot=document.getElementById('vis-dot');
  const lbl=document.getElementById('vis-label');
  document.getElementById('db-vis-dot').className=dot.className;
  document.getElementById('db-vis-lbl').textContent=lbl.textContent;
}

// ─── STATUS PANEL ───
function relativeTime(isoStr){
  if(!isoStr) return '—';
  const d=new Date(isoStr), now=new Date();
  const s=Math.round((now-d)/1000);
  if(s<5) return 'À l\'instant';
  if(s<60) return `Il y a ${s}s`;
  if(s<3600) return `Il y a ${Math.round(s/60)}min`;
  return `Il y a ${Math.round(s/3600)}h`;
}
function futureTime(isoStr){
  if(!isoStr) return '—';
  const d=new Date(isoStr), now=new Date();
  const s=Math.round((d-now)/1000);
  if(s<=0) return 'Imminente';
  if(s<60) return `Dans ${s}s`;
  if(s<3600) return `Dans ${Math.round(s/60)}min`;
  return `Dans ${Math.round(s/3600)}h`;
}

async function fetchStatus(){
  try{
    const r=await fetch('/api/status');
    if(!r.ok) return;
    const s=await r.json();
    const runEl=document.getElementById('st-running');
    if(s.running){
      runEl.textContent='⏳ En cours…'; runEl.className='status-val running';
    } else if(s.errors && s.errors.length>0 && !s.last_success){
      runEl.textContent='❌ Erreur'; runEl.className='status-val err';
    } else {
      runEl.textContent='✅ OK'; runEl.className='status-val ok';
    }
    document.getElementById('st-last').textContent=relativeTime(s.last_success)||relativeTime(s.last_attempt)||'Jamais';
    document.getElementById('st-next').textContent=futureTime(s.next_run);
    document.getElementById('st-radars').textContent=s.radars_count?s.radars_count.toLocaleString('fr-FR')+' entrées':'—';
    document.getElementById('st-cams').textContent=s.cameras_count?s.cameras_count.toLocaleString('fr-FR')+' entrées':'—';

    const errWrap=document.getElementById('st-errors-wrap');
    const errList=document.getElementById('error-list');
    if(s.errors && s.errors.length>0){
      errWrap.style.display='block';
      errList.innerHTML=s.errors.slice(0,5).map(e=>`
        <div class="error-item">${e.msg}<span class="error-time">${relativeTime(e.time)}</span></div>
      `).join('');
    } else {
      errWrap.style.display='none';
    }
  }catch(e){}
}

async function forceUpdate(){
  const btn=document.getElementById('btn-force-update');
  btn.disabled=true; btn.textContent='⏳ Mise à jour…';
  try{
    await fetch('/api/force-update',{method:'POST'});
    btn.textContent='✅ Lancée !';
    setTimeout(()=>{ btn.disabled=false; btn.textContent='🔄 Forcer la mise à jour'; },3000);
    // Poll statut plus fréquemment pendant la maj
    let polls=0;
    const interval=setInterval(async()=>{
      await fetchStatus();
      polls++;
      if(polls>60) clearInterval(interval);
    },2000);
  }catch(e){
    btn.disabled=false; btn.textContent='🔄 Forcer la mise à jour';
  }
}

document.getElementById('fab-group').addEventListener('click',e=>e.stopPropagation());
document.getElementById('settings-drawer').addEventListener('click',e=>e.stopPropagation());

// Poll statut toutes les 30s quand le drawer est ouvert
setInterval(()=>{
  if(document.getElementById('settings-drawer').classList.contains('open')) fetchStatus();
},30000);
setTimeout(fetchStatus, 1500);
document.getElementById('fab-settings').addEventListener('click',()=>{
  if(document.getElementById('settings-drawer').classList.contains('open')) fetchStatus();
});

window.addEventListener('load',initMap);
// Keep-alive Render : ping /health toutes les 14min pour éviter le sleep
setInterval(()=>fetch('/health').catch(()=>{}), 14*60*1000);
</script>
</body>
</html>"""
    return Response(html, mimetype='text/html')

if __name__ == '__main__':
    scheduled_update()
    app.run(host='0.0.0.0', port=8080)
