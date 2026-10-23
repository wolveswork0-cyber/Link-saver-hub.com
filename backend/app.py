from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import yt_dlp
import tempfile
import uuid
import os
from pathlib import Path

app = Flask(__name__)
CORS(app)

# Temporary download folder
BASE = Path(tempfile.gettempdir()) / "linkdrop_pro"
BASE.mkdir(parents=True, exist_ok=True)

# Deno on Render
DENO_PATH = "/opt/render/.deno/bin/deno"

# Make Deno available to yt-dlp
if os.path.exists(DENO_PATH):
    os.environ["PATH"] = (
        "/opt/render/.deno/bin:"
        + os.environ.get("PATH", "")
    )


@app.get("/")
def home():
    return jsonify({
        "name": "LinkDrop PRO API",
        "status": "online"
    })


@app.post("/api/download")
def download():
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()

    if not url.startswith(("http://", "https://")):
        return jsonify({
            "error": "Enter a valid http/https URL."
        }), 400

    folder = BASE / uuid.uuid4().hex
    folder.mkdir(parents=True, exist_ok=True)

    template = str(folder / "%(title).120s.%(ext)s")

    options = {
        "outtmpl": template,
        "noplaylist": True,

        "quiet": False,
        "no_warnings": False,

        "format": "bestvideo*+bestaudio/best",

        # Deno JavaScript runtime
        "js_runtimes": {
            "deno": {
                "path": DENO_PATH
            }
        },

        # yt-dlp EJS
        "remote_components": [
            "ejs:github"
        ],

        # Force IPv4
        "source_address": "0.0.0.0",

        # YouTube client configuration
        "extractor_args": {
            "youtube": {
                "player_client": [
                    "web_safari",
                    "web_embedded",
                    "-tv_downgraded"
                ]
            }
        },

        "socket_timeout": 30,
        "retries": 3,
        "fragment_retries": 3,
    }

    # Optional proxy.
    # If YTDLP_PROXY is added in Render Environment Variables,
    # yt-dlp will use it.
    proxy = os.environ.get("YTDLP_PROXY", "").strip()

    if proxy:
        options["proxy"] = proxy

    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = Path(ydl.prepare_filename(info))

        # Final file extension can change after merging
        if not filename.exists():
            files = list(folder.iterdir())

            if not files:
                return jsonify({
                    "error": "No downloadable media returned."
                }), 404

            filename = files[0]

        return send_file(
            filename,
            as_attachment=True,
            download_name=filename.name
        )

    except Exception as e:
        return jsonify({
            "error": "URL could not be downloaded.",
            "details": str(e)[:2000]
        }), 400


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8080))
    )
