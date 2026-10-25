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

DENO_PATH = "/opt/render/.deno/bin/deno"
BGUTIL_SERVER = "/opt/render/bgutil-ytdlp-pot-provider/server"
BGUTIL_NODE_MODULES = "/opt/render/bgutil-ytdlp-pot-provider/server/node_modules"
BGUTIL_PORT = "4416"

if os.path.exists(DENO_PATH):
    os.environ["PATH"] = (
        "/opt/render/.deno/bin:"
        + os.environ.get("PATH", "")
    )

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
            print("BGUTIL PO Token server started on 127.0.0.1:4416")
        else:
            print("BGUTIL START FAILED")

    except Exception as e:
        print("BGUTIL START ERROR:", repr(e))


start_bgutil()


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
    download_format = (data.get("format") or "mp4").lower()
    quality = (data.get("quality") or "best").lower()

    if not url.startswith(("http://", "https://")):
        return jsonify({
            "error": "Enter a valid http/https URL."
        }), 400

    folder = BASE / uuid.uuid4().hex
    folder.mkdir(parents=True, exist_ok=True)

    template = str(
        folder / "%(title).120s.%(ext)s"
    )

    # -----------------------------
    # FORMAT / QUALITY
    # -----------------------------

    if download_format == "mp3":

        format_selector = "bestaudio/best"

        postprocessors = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ]

        merge_format = None

    else:

        if quality == "480":
            height = 480

        elif quality == "720":
            height = 720

        elif quality == "1080":
            height = 1080

        else:
            height = None

        if height:
            format_selector = (
                f"bestvideo[height<={height}]"
                f"+bestaudio/"
                f"best[height<={height}]"
            )
        else:
            format_selector = (
                "bestvideo*+bestaudio/best"
            )

        postprocessors = []
        merge_format = "mp4"

    # -----------------------------
    # YT-DLP OPTIONS
    # -----------------------------

    options = {
        "outtmpl": template,
        "noplaylist": True,

        "quiet": False,
        "no_warnings": False,

        "format": format_selector,

        "merge_output_format": merge_format,

        "postprocessors": postprocessors,

        "js_runtimes": {
            "deno": {
                "path": DENO_PATH
            }
        },

        "remote_components": [
            "ejs:github"
        ],

        "extractor_args": {
            "youtube": {
                "player_client": [
                    "mweb",
                    "web_safari"
                ]
            },

            "youtubepot-bgutilhttp": {
                "base_url":
                    "http://127.0.0.1:4416"
            }
        },

        "source_address": "0.0.0.0",

        "socket_timeout": 30,

        "retries": 3,
        "fragment_retries": 3,
        "extractor_retries": 3,
    }

    proxy = os.environ.get(
        "YTDLP_PROXY",
        ""
    ).strip()

    if proxy:
        options["proxy"] = proxy

    try:

        print("===================================")
        print("Downloading:", url)
        print("Format:", download_format)
        print("Quality:", quality)
        print("===================================")

        with yt_dlp.YoutubeDL(options) as ydl:

            info = ydl.extract_info(
                url,
                download=True
            )

        # -----------------------------
        # FIND FINAL FILE
        # -----------------------------

        files = [
            f for f in folder.iterdir()
            if f.is_file()
        ]

        if not files:
            return jsonify({
                "error":
                    "No downloadable media returned."
            }), 404

        if download_format == "mp3":

            mp3_files = [
                f for f in files
                if f.suffix.lower() == ".mp3"
            ]

            filename = (
                mp3_files[0]
                if mp3_files
                else files[0]
            )

        else:

            mp4_files = [
                f for f in files
                if f.suffix.lower() == ".mp4"
            ]

            filename = (
                mp4_files[0]
                if mp4_files
                else files[0]
            )

        print(
            "Download completed:",
            filename
        )

        # -----------------------------
        # SEND FILE
        # -----------------------------

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
