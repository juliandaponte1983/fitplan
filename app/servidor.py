"""Arranca la web local:  python -m app.servidor  (abre el navegador en http://127.0.0.1:8720)."""
import threading
import webbrowser

import uvicorn

PUERTO = 8720

if __name__ == "__main__":
    threading.Timer(1.2, lambda: webbrowser.open(f"http://127.0.0.1:{PUERTO}")).start()
    uvicorn.run("app.main:app", host="127.0.0.1", port=PUERTO, log_level="warning")
