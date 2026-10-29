import os
import sys
import subprocess

port = os.environ.get('PORT', os.environ.get('SERVER_PORT', '8501'))
sys.path.insert(0, os.path.dirname(__file__))

cmd = [
    sys.executable, "-m", "streamlit", "run", "app.py",
    "--server.port", str(port),
    "--server.address", "127.0.0.1",
    "--server.headless", "true",
    "--server.enableCORS", "false",
    "--server.enableXsrfProtection", "false",
    "--server.enableWebsocketCompression", "false"
]

try:
    log_file = os.path.join(os.path.dirname(__file__), "streamlit.log")
    with open(log_file, "a") as log:
        subprocess.Popen(cmd, stdout=log, stderr=log)
except Exception as e:
    print(f"Erreur: {e}", file=sys.stderr)

def application(environ, start_response):
    start_response('200 OK', [('Content-Type', 'text/html; charset=utf-8')])
    html = """<html><head><meta http-equiv="refresh" content="8"><style>
    body{font-family:Arial;display:flex;justify-content:center;align-items:center;height:100vh;background:#f0f8f0}
    .box{background:white;padding:40px;border-radius:15px;box-shadow:0 10px 30px rgba(0,0,0,0.2);text-align:center}
    h2{color:#00b050}.loader{border:4px solid #f3f3f3;border-top:4px solid #00b050;border-radius:50%;width:40px;height:40px;animation:spin 1s linear infinite;margin:20px auto}
    @keyframes spin{0%{transform:rotate(0deg)}100%{transform:rotate(360deg)}}</style></head>
    <body><div class="box"><h2>🌊 Hydrometrie Gabon - DGE</h2><div class="loader"></div>
    <p>Demarrage tableau de bord...<br>Rafraichissement auto dans 8s</p></div>
    <script>setTimeout(()=>{location.reload()},8000)</script></body></html>"""
    return [html.encode('utf-8')]