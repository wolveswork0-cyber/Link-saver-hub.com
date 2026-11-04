
import os
import re
import uuid
import shutil
import logging
import threading
import subprocess
import tempfile
import socket
import time
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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s:%(name)s:%(message)s"
)
logger = logging.getLogger("LinkDropPro")

BASE_DIR = Path(tempfile.gettempdir()) / "linkdrop_pro"
BASE_DIR.mkdir(parents=True, exist_ok=True)

BGUTIL_HOST = "127.0.0.1"
BGUTIL_PORT = 4416
BGUTIL_URL = f"http://{BGUTIL_HOST}:{BGUTIL_PORT}"
BGUTIL_LOG = "/tmp/bgutil.log"

bgutil_process = None
bgutil_lock = threading.Lock()


# --------------------------------------------------
# DENO DETECTION
# --------------------------------------------------

def find_deno():

    possible_paths = [
        os.environ.get("DENO_PATH"),
        shutil.which("deno"),
        "/opt/render/.deno/bin/deno",
        "/opt/render/project/.deno/bin/deno",
        "/opt/render/project/src/.deno/bin/deno",
        str(Path.home() / ".deno" / "bin" / "deno"),
        "/usr/local/bin/deno",
    ]

    checked = []

    for path in possible_paths:

        if not path or path in checked:
            continue

        checked.append(path)

        try:
            deno_file = Path(path)

            if deno_file.is_file():

                if not os.access(path, os.X_OK):
                    try:
                        os.chmod(path, 0o755)
                    except OSError:
                        pass

                if os.access(path, os.X_OK):

                    os.environ["PATH"] = (
                        str(deno_file.parent)
                        + os.pathsep
                        + os.environ.get("PATH", "")
                    )

                    result = subprocess.run(
                        [path, "--version"],
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )

                    if result.returncode == 0:
                        logger.info(
                            "[DENO] Found: %s",
                            path
                        )
                        logger.info(
                            "[DENO] Version: %s",
                            result.stdout.strip().splitlines()[0]
                        )
                        return path

                    logger.warning(
                        "[DENO] Version check failed: %s",
                        result.stderr[-1000:]
                    )

        except Exception:
            logger.exception("[DENO] Detection error for %s", path)

    logger.error("[DENO] No working Deno executable found")
    logger.info("[DENO] PATH: %s", os.environ.get("PATH"))

    return None


DENO_PATH = str(
    Path(__file__).resolve().parent / ".deno" / "bin" / "deno"
)

if not (
    os.path.isfile(DENO_PATH)
    and os.access(DENO_PATH, os.X_OK)
):
    DENO_PATH = find_deno()


# --------------------------------------------------
# BGUTIL SERVER
# --------------------------------------------------

def find_bgutil_server():

    possible_paths = [
        Path(__file__).resolve().parent
        / "bgutil-ytdlp-pot-provider" / "server",

        Path(__file__).resolve().parent.parent
        / "bgutil-ytdlp-pot-provider" / "server",

        Path.cwd()
        / "bgutil-ytdlp-pot-provider" / "server",

        Path(
            "/opt/render/project/src/backend/"
            "bgutil-ytdlp-pot-provider/server"
        ),
    ]

    for folder in possible_paths:

        if (folder / "build" / "main.js").is_file():
            return folder

    return None


def check_bgutil_port():

    try:
        with socket.create_connection(
            (BGUTIL_HOST, BGUTIL_PORT),
            timeout=2
        ):
            return True

    except OSError:
        return False


def start_bgutil():

    global bgutil_process

    with bgutil_lock:

        if check_bgutil_port():
            logger.info("[BGUTIL] Server already responding")
            return True

        server_dir = find_bgutil_server()

        if not server_dir:
            logger.error("[BGUTIL] build/main.js NOT FOUND")
            return False

        node_path = shutil.which("node")

        if not node_path:
            logger.error("[BGUTIL] Node.js NOT FOUND")
            return False

        command = [
            node_path,
            "build/main.js",
            "--host", BGUTIL_HOST,
            "--port", str(BGUTIL_PORT),
        ]

        logger.info("[BGUTIL] Directory: %s", server_dir)
        logger.info("[BGUTIL] Node: %s", node_path)
        logger.info("[BGUTIL] Command: %s", command)

        try:

            with open(BGUTIL_LOG, "a", buffering=1) as log_file:

                bgutil_process = subprocess.Popen(
                    command,
                    cwd=str(server_dir),
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )

            logger.info(
                "[BGUTIL] Process started. PID: %s",
                bgutil_process.pid
            )

            for attempt in range(15):

                time.sleep(1)

                if check_bgutil_port():
                    logger.info(
                        "[BGUTIL] Server READY on port %s",
                        BGUTIL_PORT
                    )
                    return True

                exit_code = bgutil_process.poll()

                if exit_code is not None:

                    logger.error(
                        "[BGUTIL] Process exited: %s",
                        exit_code
                    )
                    break

            try:

                with open(BGUTIL_LOG, "r") as log_file:
                    logger.error(
                        "[BGUTIL] Logs:\n%s",
                        log_file.read()[-4000:]
                    )

            except Exception:
                logger.exception("[BGUTIL] Log read failed")

            logger.error("[BGUTIL] Port is not responding")
            return False

        except Exception:
            logger.exception("[BGUTIL] Startup failed")
            return False


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


# --------------------------------------------------
# YT-DLP OPTIONS
# --------------------------------------------------

def make_ydl_options(extra_options=None):

    options = {
        "quiet": True,
        "no_warnings": False,
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

        "remote_components": ["ejs:npm"],
    }

    # Configure Deno JavaScript runtime.

    if DENO_PATH:

        options["js_runtimes"] = {
            "deno": {
                "path": DENO_PATH,
            }
        }

        logger.info(
            "[DENO] Runtime configured: %s",
            DENO_PATH
        )

    else:

        logger.warning(
            "[DENO] Runtime unavailable. "
            "YouTube JavaScript challenges may fail."
        )

    if extra_options:
        options.update(extra_options)

    return options


# --------------------------------------------------
# HOME
# --------------------------------------------------

@app.route("/", methods=["GET"])
def home():

    return jsonify({
        "name": "LinkDrop Pro API",
        "status": "online",
    })


# --------------------------------------------------
# HEALTH CHECK
# --------------------------------------------------

@app.route("/health", methods=["GET"])
def health():

    deno_ready = False
    deno_version = None

    if DENO_PATH:

        try:

            result = subprocess.run(
                [DENO_PATH, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )

            deno_ready = result.returncode == 0

            if deno_ready and result.stdout:
                deno_version = result.stdout.splitlines()[0]

        except Exception as error:
            deno_version = str(error)

    bgutil_ready = check_bgutil_port()

    try:

        with open(BGUTIL_LOG, "r") as f:
            bgutil_logs = f.read()[-4000:]

    except Exception:
        bgutil_logs = "No BGUTIL log file"

    return jsonify({

        "status": "online",

        "deno": deno_ready,
        "deno_path": DENO_PATH,
        "deno_version": deno_version,

        "node": shutil.which("node") is not None,
        "node_path": shutil.which("node"),

        "bgutil": bgutil_ready,

        "bgutil_pid": (
            bgutil_process.pid
            if bgutil_process else None
        ),

        "bgutil_exit_code": (
            bgutil_process.poll()
            if bgutil_process else None
        ),

        "bgutil_logs": bgutil_logs,

    })


# --------------------------------------------------
# VIDEO INFORMATION
# --------------------------------------------------

@app.route("/api/info", methods=["POST", "OPTIONS"])
def video_info():

    if request.method == "OPTIONS":
        return "", 200

    data = request.get_json(silent=True) or {}
    url = data.get("url", "")

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
            info = ydl.extract_info(
                url.strip(),
                download=False
            )

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

    url = data.get("url", "")

    format_id = str(data.get("format_id", "best"))
    audio_only = bool(data.get("audio_only", False))

    if not validate_url(url):

        return jsonify({
            "success": False,
            "error": "Please enter a valid public video URL.",
        }), 400

    # Retry BGUTIL if the server is unavailable.

    if not check_bgutil_port():

        logger.warning("[BGUTIL] Restarting unavailable server")
        start_bgutil()

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
            ydl.download([url.strip()])

        downloaded_files = [

            item for item in download_dir.iterdir()

            if item.is_file()
            and not item.name.endswith((".part", ".ytdl"))

        ]

        if not downloaded_files:

            raise Exception(
                "Download completed but output file was not found"
            )

        output_file = max(
            downloaded_files,
            key=lambda item: item.stat().st_size
        )

        response = send_file(

            str(output_file),

            as_attachment=True,

            download_name=clean_filename(
                output_file.name
            ),

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
