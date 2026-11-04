import os
import re
import uuid
import shutil
import socket
import logging
import subprocess
import atexit
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from yt_dlp import YoutubeDL


# --------------------------------------------------
# APP SETTINGS
# --------------------------------------------------

app = Flask(__name__)
CORS(app)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("LinkDropPro")

BASE_DIR = Path(tempfile.gettempdir()) / "linkdrop_pro"

# BGUTIL POT provider
BGUTIL_URL = "http://127.0.0.1:4416"
BGUTIL_DIR = Path(__file__).resolve().parent / "bgutil-ytdlp-pot-provider"

# Deno installed by Render Build Command
DENO_PATH = (
    Path(__file__).resolve().parent
    / ".deno"
    / "bin"
    / "deno"
)

BASE_DIR.mkdir(parents=True, exist_ok=True)


# --------------------------------------------------
# START BGUTIL SERVER
# --------------------------------------------------

bgutil_process = None


def start_bgutil():
    global bgutil_process

    server_file = BGUTIL_DIR / "server" / "build" / "main.js"

    if not server_file.exists():
        logger.warning("[BGUTIL] Server build not found: %s", server_file)
        return

    node_path = shutil.which("node")

    if not node_path:
        logger.warning("[BGUTIL] Node.js not found")
        return

    try:
        bgutil_process = subprocess.Popen(
            [
                node_path,
                str(server_file),
                "--host",
                "127.0.0.1",
                "--port",
                "4416",
            ],
            cwd=str(BGUTIL_DIR / "server"),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
        )

        logger.info("[BGUTIL] Server process started")

    except Exception as error:
        logger.exception("[BGUTIL] Could not start: %s", error)


def is_bgutil_running():
    try:
        with socket.create_connection(("127.0.0.1", 4416), timeout=2):
            return True
    except OSError:
        return False


def stop_bgutil():
    global bgutil_process

    if bgutil_process and bgutil_process.poll() is None:
        bgutil_process.terminate()


start_bgutil()
atexit.register(stop_bgutil)


# --------------------------------------------------
# URL HELPERS
# --------------------------------------------------

def is_valid_url(url):
    try:
        parsed = urlparse(url)

        return (
            parsed.scheme in ("http", "https")
            and bool(parsed.netloc)
        )

    except Exception:
        return False


def is_snapchat_url(url):
    try:
        host = (urlparse(url).hostname or "").lower()

        return (
            host == "snapchat.com"
            or host.endswith(".snapchat.com")
        )

    except Exception:
        return False


def format_filesize(size):
    if not size:
        return "Unknown"

    size = float(size)

    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024:
            return f"{size:.2f} {unit}"

        size /= 1024

    return f"{size:.2f} TB"


def format_duration(seconds):
    if not seconds:
        return "Unknown"

    seconds = int(seconds)

    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60

    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"

    return f"{minutes}:{secs:02d}"


# --------------------------------------------------
# YT-DLP OPTIONS
# --------------------------------------------------

def make_ydl_options(extra_options=None, source_url=None):

    options = {
        "quiet": True,
        "no_warnings": False,
        "noplaylist": True,

        "socket_timeout": 30,
        "retries": 3,
        "fragment_retries": 3,

        "format": "best[ext=mp4]/best",

        "extractor_args": {
            "youtube": {
                "player_client": ["android"],
            },

            "youtubepot-bgutilhttp": {
                "base_url": BGUTIL_URL,
            },
        },

        "remote_components": ["ejs:npm"],
    }

    # Deno JavaScript runtime
    if DENO_PATH.exists():
        options["js_runtimes"] = {
            "deno": {
                "path": str(DENO_PATH),
            }
        }

        logger.info("[DENO] Runtime configured: %s", DENO_PATH)

    else:
        logger.warning("[DENO] Runtime not found")

    # Snapchat browser impersonation
    if source_url and is_snapchat_url(source_url):
        options["impersonate"] = "chrome"
        logger.info("[SNAPCHAT] Chrome impersonation enabled")

    if extra_options:
        options.update(extra_options)

    return options


# --------------------------------------------------
# EXTRACT INFO WITH SNAPCHAT FALLBACK
# --------------------------------------------------

def extract_info_with_fallback(url, options):

    try:
        with YoutubeDL(options) as ydl:
            return ydl.extract_info(
                url.strip(),
                download=False
            )

    except Exception:

        if not is_snapchat_url(url):
            raise

        logger.warning(
            "[SNAPCHAT] Primary extractor failed. "
            "Trying Generic Extractor."
        )

        fallback_options = dict(options)
        fallback_options["force_generic_extractor"] = True

        with YoutubeDL(fallback_options) as ydl:
            return ydl.extract_info(
                url.strip(),
                download=False
            )


# --------------------------------------------------
# HOME ROUTE
# --------------------------------------------------

@app.route("/", methods=["GET"])
def home():

    return jsonify({
        "name": "LinkDrop Pro API",
        "status": "online",
        "message": "Universal Link Downloader API is running"
    })


# --------------------------------------------------
# HEALTH CHECK
# --------------------------------------------------

@app.route("/health", methods=["GET"])
def health():

    deno_ok = DENO_PATH.exists()
    bgutil_ok = is_bgutil_running()

    return jsonify({
        "status": "online",
        "deno": deno_ok,
        "deno_path": str(DENO_PATH) if deno_ok else None,
        "bgutil": bgutil_ok,
        "node": shutil.which("node") is not None,
    })


# --------------------------------------------------
# VIDEO INFORMATION API
# --------------------------------------------------

@app.route("/api/info", methods=["POST", "OPTIONS"])
def video_info():

    if request.method == "OPTIONS":
        return "", 204

    data = request.get_json(silent=True) or {}
    url = str(data.get("url", "")).strip()

    if not is_valid_url(url):
        return jsonify({
            "success": False,
            "error": "Enter a valid video URL."
        }), 400

    try:

        options = make_ydl_options({
            "skip_download": True,
            "extract_flat": False,
        }, source_url=url)

        info = extract_info_with_fallback(url, options)

        formats = []

        for item in info.get("formats", []):

            if not item.get("url"):
                continue

            formats.append({
                "format_id": item.get("format_id"),
                "ext": item.get("ext"),
                "resolution": (
                    item.get("resolution")
                    or (
                        f'{item.get("width")}x{item.get("height")}'
                        if item.get("height")
                        else "Unknown"
                    )
                ),
                "filesize": item.get("filesize"),
                "filesize_text": format_filesize(
                    item.get("filesize")
                    or item.get("filesize_approx")
                ),
                "format_note": item.get("format_note"),
            })

        return jsonify({
            "success": True,
            "title": info.get("title") or "Video",
            "thumbnail": info.get("thumbnail"),
            "duration": info.get("duration"),
            "duration_string": format_duration(
                info.get("duration")
            ),
            "uploader": info.get("uploader"),
            "filesize": (
                info.get("filesize")
                or info.get("filesize_approx")
            ),
            "filesize_text": format_filesize(
                info.get("filesize")
                or info.get("filesize_approx")
            ),
            "formats": formats,
        })

    except Exception as error:

        logger.exception("[INFO] Extraction failed")

        return jsonify({
            "success": False,
            "error": str(error)[:1000],
        }), 400


# --------------------------------------------------
# VIDEO DOWNLOAD API
# --------------------------------------------------

@app.route("/api/download", methods=["POST", "OPTIONS"])
def download_video():

    if request.method == "OPTIONS":
        return "", 204

    data = request.get_json(silent=True) or {}
    url = str(data.get("url", "")).strip()

    if not is_valid_url(url):
        return jsonify({
            "error": "Enter a valid http/https URL."
        }), 400

    download_dir = BASE_DIR / str(uuid.uuid4())
    download_dir.mkdir(parents=True, exist_ok=True)

    try:

        output_template = str(
            download_dir / "%(title).120s.%(ext)s"
        )

        options = make_ydl_options({
            "outtmpl": output_template,
            "noplaylist": True,
            "overwrites": True,
        }, source_url=url)

        # First normal download attempt
        try:

            with YoutubeDL(options) as ydl:
                ydl.download([url])

        except Exception:

            if not is_snapchat_url(url):
                raise

            logger.warning(
                "[SNAPCHAT] Download fallback activated"
            )

            # Remove partial files before retry
            for item in download_dir.iterdir():

                if item.is_file():
                    item.unlink()

                elif item.is_dir():
                    shutil.rmtree(
                        item,
                        ignore_errors=True
                    )

            fallback_options = dict(options)
            fallback_options["force_generic_extractor"] = True

            with YoutubeDL(fallback_options) as ydl:
                ydl.download([url])

        # Find downloaded media file
        downloaded_files = [
            file for file in download_dir.iterdir()
            if file.is_file()
            and not file.name.endswith((".part", ".ytdl"))
        ]

        if not downloaded_files:
            raise Exception(
                "No downloadable media file was created."
            )

        # Select largest downloaded file
        filename = max(
            downloaded_files,
            key=lambda file: file.stat().st_size
        )

        response = send_file(
            filename,
            as_attachment=True,
            download_name=filename.name
        )

        # Delete temporary files after response is sent
        response.call_on_close(
            lambda: shutil.rmtree(
                download_dir,
                ignore_errors=True
            )
        )

        return response

    except Exception as error:

        logger.exception("[DOWNLOAD] Download failed")

        shutil.rmtree(
            download_dir,
            ignore_errors=True
        )

        return jsonify({
            "error": "URL could not be downloaded.",
            "details": str(error)[:1000],
        }), 400


# --------------------------------------------------
# LOCAL START
# --------------------------------------------------

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000))
    )
