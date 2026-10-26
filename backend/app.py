from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from pathlib import Path
import subprocess
import shutil
import tempfile
import uuid
import time
import os
import threading

import yt_dlp


app = Flask(__name__)
CORS(app)


# =========================================================
# PATHS
# =========================================================

APP_DIR = Path(__file__).resolve().parent

DOWNLOAD_BASE = Path(tempfile.gettempdir()) / "linkdrop_pro"
DOWNLOAD_BASE.mkdir(parents=True, exist_ok=True)

BGUTIL_SERVER = APP_DIR / "bgutil-ytdlp-pot-provider" / "server"
BGUTIL_BUILD = BGUTIL_SERVER / "build" / "main.js"

BGUTIL_PORT = 4416
BGUTIL_PROCESS = None


# =========================================================
# START BGUTIL PO TOKEN SERVER
# =========================================================

def start_bgutil():
    global BGUTIL_PROCESS

    print("Starting BGUTIL PO Token server...")

    node_path = shutil.which("node")

    if not node_path:
        print("BGUTIL START ERROR: Node.js not found")
        return

    if not BGUTIL_BUILD.exists():
        print(f"BGUTIL START ERROR: build/main.js not found: {BGUTIL_BUILD}")
        return

    try:
        BGUTIL_PROCESS = subprocess.Popen(
            [
                node_path,
                str(BGUTIL_BUILD),
                "--port",
                str(BGUTIL_PORT),
                "--host",
                "127.0.0.1",
            ],
            cwd=str(BGUTIL_SERVER),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        print(
            f"BGUTIL PO Token server started "
            f"(PID={BGUTIL_PROCESS.pid}, port={BGUTIL_PORT})"
        )

        def read_output():
            try:
                for line in BGUTIL_PROCESS.stdout:
                    print(f"[BGUTIL] {line.rstrip()}")
            except Exception as e:
                print(f"[BGUTIL OUTPUT ERROR] {e}")

        threading.Thread(
            target=read_output,
            daemon=True
        ).start()

        time.sleep(2)

        if BGUTIL_PROCESS.poll() is not None:
            print(
                f"BGUTIL PROCESS EXITED "
                f"with code {BGUTIL_PROCESS.returncode}"
            )
        else:
            print("BGUTIL PO Token server is running.")

    except Exception as e:
        print(f"BGUTIL START ERROR: {repr(e)}")


# Start BGUTIL when Gunicorn worker loads this module
start_bgutil()


# =========================================================
# HOME
# =========================================================

@app.route("/", methods=["GET", "HEAD"])
def home():
    return jsonify({
        "name": "LinkDrop PRO API",
        "status": "online"
    })


# =========================================================
# DOWNLOAD
# =========================================================

@app.route("/api/download", methods=["POST", "OPTIONS"])
def download():

    if request.method == "OPTIONS":
        return "", 200

    data = request.get_json(silent=True) or {}

    url = str(data.get("url", "")).strip()
    fmt = str(data.get("format", "mp4")).lower().strip()
    quality = str(data.get("quality", "best")).lower().strip()

    if not url:
        return jsonify({
            "error": "URL is required"
        }), 400

    if not url.startswith(("http://", "https://")):
        return jsonify({
            "error": "Invalid URL"
        }), 400

    job_id = str(uuid.uuid4())
    job_dir = DOWNLOAD_BASE / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    output_template = str(job_dir / "%(title).120s.%(ext)s")

    # =====================================================
    # FORMAT SELECTION
    # =====================================================

    if fmt == "mp3":

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
            format_selector = (
                "bestvideo[height<=480]+bestaudio/"
                "best[height<=480]/best"
            )

        elif quality == "720":
            format_selector = (
                "bestvideo[height<=720]+bestaudio/"
                "best[height<=720]/best"
            )

        elif quality == "1080":
            format_selector = (
                "bestvideo[height<=1080]+bestaudio/"
                "best[height<=1080]/best"
            )

        else:
            format_selector = (
                "bestvideo*+bestaudio/"
                "best"
            )

        postprocessors = []

        merge_format = "mp4"


    # =====================================================
    # YT-DLP OPTIONS
    # =====================================================

    ydl_opts = {
        "outtmpl": output_template,

        "format": format_selector,

        "noplaylist": True,

        "quiet": False,
        "no_warnings": False,

        "merge_output_format": merge_format,

        "retries": 3,
        "fragment_retries": 3,

        "socket_timeout": 60,

        "concurrent_fragment_downloads": 4,

        "postprocessors": postprocessors,

        # BGUTIL PO Token provider
        "extractor_args": {
            "youtube": {
                "player_client": ["web"],
            },
            "youtubepot-bgutilhttp": {
                "base_url": f"http://127.0.0.1:{BGUTIL_PORT}"
            },
        },

        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/140.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        },
    }


    # =====================================================
    # DOWNLOAD
    # =====================================================

    try:

        print("========================================")
        print("DOWNLOAD REQUEST")
        print(f"URL: {url}")
        print(f"FORMAT: {fmt}")
        print(f"QUALITY: {quality}")
        print("========================================")

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:

            info = ydl.extract_info(
                url,
                download=True
            )

            print("Download completed.")

        # =================================================
        # FIND OUTPUT FILE
        # =================================================

        files = [
            p for p in job_dir.iterdir()
            if p.is_file()
        ]

        if not files:
            raise RuntimeError(
                "Download completed but output file was not found."
            )

        # Prefer requested format
        if fmt == "mp3":

            preferred = [
                p for p in files
                if p.suffix.lower() == ".mp3"
            ]

        else:

            preferred = [
                p for p in files
                if p.suffix.lower() == ".mp4"
            ]

        if preferred:
            output_file = preferred[0]
        else:
            output_file = files[0]

        print(f"OUTPUT FILE: {output_file}")

        # =================================================
        # SEND FILE
        # =================================================

        download_name = output_file.name

        response = send_file(
            str(output_file),
            as_attachment=True,
            download_name=download_name
        )

        return response

    except Exception as e:

        print("DOWNLOAD ERROR:")
        print(repr(e))

        return jsonify({
            "error": "Download failed",
            "details": str(e)
        }), 500

    finally:

        # Cleanup is intentionally delayed so send_file
        # has enough time to read the file.
        def cleanup():

            try:
                time.sleep(300)

                if job_dir.exists():
                    shutil.rmtree(
                        job_dir,
                        ignore_errors=True
                    )

            except Exception:
                pass

        threading.Thread(
            target=cleanup,
            daemon=True
        ).start()


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            "10000"
        )
    )

    app.run(
        host="0.0.0.0",
        port=port
                  )
