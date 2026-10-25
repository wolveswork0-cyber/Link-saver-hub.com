from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import yt_dlp
import tempfile
import uuid
import os
import subprocess
import time
from pathlib import Path

app = Flask(__name__)
CORS(app)

BASE = Path(tempfile.gettempdir()) / "linkdrop_pro"
BASE.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------
# Paths
# ---------------------------------------------------------

DENO_PATH = "/opt/render/.deno/bin/deno"
BGUTIL_SERVER = "/opt/render/bgutil-ytdlp-pot-provider/server"
BGUTIL_NODE_MODULES = "/opt/render/bgutil-ytdlp-pot-provider/server/node_modules"
BGUTIL_PORT = "4416"

# ---------------------------------------------------------
# Environment
# ---------------------------------------------------------

if os.path.exists(DENO_PATH):
    os.environ["PATH"] = (
        "/opt/render/.deno/bin:"
        + os.environ.get("PATH", "")
    )

# ---------------------------------------------------------
# Start BGUTIL PO Token Server
# ---------------------------------------------------------

_bgutil_process = None


def start_bgutil():
    global _bgutil_process

    if _bgutil_process is not None:
        return

    if not os.path.isdir(BGUTIL_NODE_MODULES):
        print("BGUTIL ERROR: node_modules folder not found")
        print("Expected:", BGUTIL_NODE_MODULES)
        return

    try:
        print("Starting BGUTIL PO Token server...")

        _bgutil_process = subprocess.Popen(
            [
                DENO_PATH,
                "run",
                "--allow-env",
                "--allow-net",
                "--allow-ffi=.",
                "--allow-read=.",
                "../src/main.ts",
                "--port",
                BGUTIL_PORT,
                "--host",
                "127.0.0.1",
            ],
            cwd=BGUTIL_NODE_MODULES,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=os.environ.copy(),
        )

        time.sleep(5)

        if _bgutil_process.poll() is None:
            print(
                "BGUTIL PO Token server started "
                "on 127.0.0.1:4416"
            )
        else:
            output = ""

            if _bgutil_process.stdout:
                try:
                    output = _bgutil_process.stdout.read()
                except Exception:
                    pass

            print("BGUTIL START FAILED")
            print(output)

    except Exception as e:
        print("BGUTIL START ERROR:", repr(e))


start_bgutil()

# ---------------------------------------------------------
# Home
# ---------------------------------------------------------


@app.get("/")
def home():
    return jsonify({
        "name": "LinkDrop PRO API",
        "status": "online"
    })


# ---------------------------------------------------------
# Download
# ---------------------------------------------------------


@app.post("/api/download")
def download():

    data = request.get_json(silent=True) or {}

    url = (data.get("url") or "").strip()

    if not url.startswith(("http://", "https://")):
        return jsonify({
            "error": "Enter a valid http/https URL."
        }), 400

    folder = BASE / uuid.uuid4().hex
    folder.mkdir(
        parents=True,
        exist_ok=True
    )

    template = str(
        folder / "%(title).120s.%(ext)s"
    )

    options = {
        # Output
        "outtmpl": template,

        # Playlist
        "noplaylist": True,

        # Logging
        "quiet": False,
        "no_warnings": False,

        # Best available media
        "format": "bestvideo*+bestaudio/best",

        # -------------------------------------------------
        # JavaScript runtime
        # -------------------------------------------------

        "js_runtimes": {
            "deno": {
                "path": DENO_PATH
            }
        },

        # -------------------------------------------------
        # Remote EJS
        # -------------------------------------------------

        "remote_components": [
            "ejs:github"
        ],

        # -------------------------------------------------
        # YouTube
        # -------------------------------------------------

        "extractor_args": {

            "youtube": {
                "player_client": [
                    "mweb",
                    "web_safari"
                ]
            },

            # BGUTIL HTTP PO Token provider
            "youtubepot-bgutilhttp": {
                "base_url":
                    "http://127.0.0.1:4416"
            }
        },

        # -------------------------------------------------
        # Network
        # -------------------------------------------------

        "source_address": "0.0.0.0",

        "socket_timeout": 30,

        "retries": 3,

        "fragment_retries": 3,

        "extractor_retries": 3,
    }

    # -----------------------------------------------------
    # Optional proxy
    # -----------------------------------------------------

    proxy = os.environ.get(
        "YTDLP_PROXY",
        ""
    ).strip()

    if proxy:
        options["proxy"] = proxy

    # -----------------------------------------------------
    # Download
    # -----------------------------------------------------

    try:

        print("Downloading:", url)

        with yt_dlp.YoutubeDL(options) as ydl:

            info = ydl.extract_info(
                url,
                download=True
            )

            filename = Path(
                ydl.prepare_filename(info)
            )

        # -------------------------------------------------
        # Fallback filename
        # -------------------------------------------------

        if not filename.exists():

            files = list(
                folder.iterdir()
            )

            if not files:
                return jsonify({
                    "error":
                        "No downloadable media returned."
                }), 404

            filename = files[0]

        print(
            "Download completed:",
            filename
        )

        return send_file(
            filename,
            as_attachment=True,
            download_name=filename.name
        )

    except Exception as e:

        print(
            "DOWNLOAD ERROR:",
            repr(e)
        )

        return jsonify({
            "error":
                "URL could not be downloaded.",
            "details":
                str(e)[:2000]
        }), 400


# ---------------------------------------------------------
# Local development
# ---------------------------------------------------------


if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=int(
            os.environ.get(
                "PORT",
                8080
            )
        )
    )
