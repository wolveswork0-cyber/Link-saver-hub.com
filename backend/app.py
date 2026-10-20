from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import yt_dlp
import tempfile
import uuid
import os
from pathlib import Path

# Make Deno available at runtime
DENO_PATH = "/opt/render/.deno/bin"
os.environ["PATH"] = DENO_PATH + ":" + os.environ.get("PATH", "")

app = Flask(__name__)
CORS(app)

BASE = Path(tempfile.gettempdir()) / "linkdrop_pro"
BASE.mkdir(parents=True, exist_ok=True)


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

        # Show useful yt-dlp logs in Render
        "quiet": False,
        "no_warnings": False,

        # Best available video/audio
        "format": "bestvideo*+bestaudio/best",

        # YouTube JavaScript runtime
        "js_runtimes": {
    "deno": {
        "path": "/opt/render/.deno/bin/deno",
        "args":
    }
},
            }
        },

        # yt-dlp EJS remote component
        "remote_components": [
            "ejs:github"
        ],

        # Network settings
        "socket_timeout": 30,
        "retries": 3,
        "fragment_retries": 3,

        # Avoid playlists
        "noplaylist": True,
    }

    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = Path(ydl.prepare_filename(info))

        # Fallback if prepared filename does not exist
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
            "details": str(e)[:1500]
        }), 400

    finally:
        # Do not delete the file here because send_file still needs it.
        pass


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8080))
    )
