
import os
import re
import uuid
import shutil
import logging
import threading
import subprocess
import tempfile
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
BASE_DIR.mkdir(parents=True, exist_ok=True)

DENO_PATH = "/opt/render/.deno/bin/deno"
BGUTIL_PORT = 4416
BGUTIL_URL = f"http://127.0.0.1:{BGUTIL_PORT}"

bgutil_process = None
bgutil_lock = threading.Lock()


# --------------------------------------------------
# BGUTIL SERVER
# --------------------------------------------------

def find_bgutil_server():
    possible_paths = [
        Path(__file__).resolve().parent / "bgutil-ytdlp-pot-provider" / "server",
        Path(__file__).resolve().parent.parent / "bgutil-ytdlp-pot-provider" / "server",
        Path.cwd() / "bgutil-ytdlp-pot-provider" / "server",
        Path("/opt/render/project/src/bgutil-ytdlp-pot-provider/server"),
        Path("/opt/render/bgutil-ytdlp-pot-provider/server"),
    ]

    for folder in possible_paths:
        if (folder / "build" / "main.js").exists():
            return folder

    return None


def start_bgutil():
    global bgutil_process

    with bgutil_lock:
        if bgutil_process and bgutil_process.poll() is None:
            return

        server_dir = find_bgutil_server()

        if not server_dir:
            logger.error("[BGUTIL] server/build/main.js not found")
            return

        node_path = shutil.which("node")

        if not node_path:
            logger.error("[BGUTIL] Node.js executable not found")
            return

        command = [node_path, "build/main.js"]

        try:
            bgutil_process = subprocess.Popen(
                command,
                cwd=str(server_dir),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )

            logger.info("[BGUTIL] Server starting at %s", BGUTIL_URL)

        except Exception:
            logger.exception("[BGUTIL] Could not start server")


start_bgutil()


# --------------------------------------------------
# HELPERS
# --------------------------------------------------

def validate_url(url):
    if not url or not isinstance(url, str):
        return False

    try:
        parsed = urlparse(url.strip())
        return (
            parsed.scheme in ("http", "https")
            and bool(parsed.netloc)
        )
    except Exception:
        return False


def clean_filename(name):
    name = str(name or "LinkDrop_download")
    name = re.sub(r'[\\/*?:"<>|]', "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name[:150] or "LinkDrop_download"


def format_size(size):
    if not size:
        return "Unknown"

    try:
        size = float(size)

        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size < 1024 or unit == "TB":
                return f"{size:.2f} {unit}"
            size /= 1024

    except (ValueError, TypeError):
        pass

    return "Unknown"


def make_ydl_options(extra_options=None):
    options = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "socket_timeout": 30,
        "retries": 3,
        "fragment_retries": 3,
        "extractor_args": {
            "youtube": {
                "player_client": ["mweb"],
            },
            "youtubepot-bgutilhttp": {
                "base_url": BGUTIL_URL,
            },
        },
        "remote_components": {"ejs:npm"},
    }

    if os.path.isfile(DENO_PATH) and os.access(DENO_PATH, os.X_OK):
        options["js_runtimes"] = {
            "deno": {"path": DENO_PATH}
        }
        logger.info("[DENO] Deno runtime configured")
    else:
        logger.warning("[DENO] Deno not found at %s", DENO_PATH)

    if extra_options:
        options.update(extra_options)

    return options


# --------------------------------------------------
# HOME AND HEALTH
# --------------------------------------------------

@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "name": "LinkDrop Pro API",
        "status": "online",
    })


@app.route("/health", methods=["GET"])
def health():
    deno_ready = (
        os.path.isfile(DENO_PATH)
        and os.access(DENO_PATH, os.X_OK)
    )

    bgutil_ready = (
        bgutil_process is not None
        and bgutil_process.poll() is None
    )

    return jsonify({
        "status": "online",
        "deno": deno_ready,
        "bgutil": bgutil_ready,
    })


# --------------------------------------------------
# VIDEO INFORMATION
# --------------------------------------------------

@app.route("/api/info", methods=["POST", "OPTIONS"])
def video_info():
    if request.method == "OPTIONS":
        return "", 200

    data = request.get_json(silent=True) or {}
    url = data.get("url", "").strip()

    if not validate_url(url):
        return jsonify({
            "success": False,
            "error": "Please enter a valid public video URL.",
        }), 400

    try:
        options = make_ydl_options({
            "skip_download": True,
            "extract_flat": False,
        })

        with YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=False)

        if not info:
            raise Exception("Could not retrieve video information")

        formats = []

        for item in info.get("formats", []):
            if not item.get("url"):
                continue

            if item.get("vcodec") == "none":
                continue

            height = item.get("height")
            filesize = (
                item.get("filesize")
                or item.get("filesize_approx")
            )

            formats.append({
                "format_id": item.get("format_id"),
                "quality": (
                    f"{height}p"
                    if height
                    else item.get("format_note", "Video")
                ),
                "ext": item.get("ext"),
                "filesize": filesize,
                "filesize_text": format_size(filesize),
            })

        return jsonify({
            "success": True,
            "title": info.get("title", "Video"),
            "thumbnail": info.get("thumbnail"),
            "duration": info.get("duration"),
            "duration_string": info.get("duration_string"),
            "uploader": info.get("uploader"),
            "filesize": (
                info.get("filesize")
                or info.get("filesize_approx")
            ),
            "filesize_text": format_size(
                info.get("filesize")
                or info.get("filesize_approx")
            ),
            "formats": formats,
        })

    except Exception as error:
        logger.exception("[INFO ERROR]")

        return jsonify({
            "success": False,
            "error": str(error),
        }), 500


# --------------------------------------------------
# VIDEO DOWNLOAD
# --------------------------------------------------

@app.route("/api/download", methods=["POST", "OPTIONS"])
def download_video():
    if request.method == "OPTIONS":
        return "", 200

    data = request.get_json(silent=True) or {}

    url = data.get("url", "").strip()
    format_id = str(data.get("format_id", "best"))
    audio_only = bool(data.get("audio_only", False))

    if not validate_url(url):
        return jsonify({
            "success": False,
            "error": "Please enter a valid public video URL.",
        }), 400

    download_id = str(uuid.uuid4())
    download_dir = BASE_DIR / download_id
    download_dir.mkdir(parents=True, exist_ok=True)

    output_template = str(
        download_dir / "%(title).120s.%(ext)s"
    )

    options = make_ydl_options({
        "outtmpl": output_template,
        "noplaylist": True,
        "overwrites": True,
    })

    if audio_only:
        options.update({
            "format": "bestaudio/best",
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }],
        })
    else:
        if format_id == "best":
            options["format"] = "bestvideo*+bestaudio/best"
            options["merge_output_format"] = "mp4"
        else:
            options["format"] = format_id

    try:
        with YoutubeDL(options) as ydl:
            ydl.download([url])

        files = [
            item for item in download_dir.iterdir()
            if item.is_file()
            and not item.name.endswith((".part", ".ytdl"))
        ]

        if not files:
            raise Exception(
                "Download completed but output file was not found"
            )

        output_file = max(
            files,
            key=lambda item: item.stat().st_size
        )

        response = send_file(
            str(output_file),
            as_attachment=True,
            download_name=clean_filename(output_file.name),
        )

        response.call_on_close(
            lambda: shutil.rmtree(
                download_dir,
                ignore_errors=True
            )
        )

        return response

    except Exception as error:
        logger.exception("[DOWNLOAD ERROR]")

        shutil.rmtree(
            download_dir,
            ignore_errors=True
        )

        return jsonify({
            "success": False,
            "error": str(error),
        }), 500


# --------------------------------------------------
# START APP
# --------------------------------------------------

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 10000)),
    )
