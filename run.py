from __future__ import annotations

import os
import threading
import webbrowser

import uvicorn

from app.config import BASE_URL, HOST, LAN_ENABLED, PORT


def main() -> None:
    open_url = BASE_URL
    if LAN_ENABLED:
        print(f"TuneBridge LAN: {BASE_URL}", flush=True)
        print("Phone: same Wi-Fi as this computer", flush=True)
        print("Stop: Ctrl+C", flush=True)
        if HOST in {"0.0.0.0", "::"}:
            open_url = f"http://127.0.0.1:{PORT}"
    else:
        print(f"TuneBridge: {BASE_URL}", flush=True)
        print("Stop: Ctrl+C", flush=True)
    if os.environ.get("TUNEBRIDGE_OPEN_BROWSER", "1") != "0":
        threading.Timer(1.2, webbrowser.open, args=(open_url,)).start()
    uvicorn.run("app.main:app", host=HOST, port=PORT, log_level="info")


if __name__ == "__main__":
    main()
