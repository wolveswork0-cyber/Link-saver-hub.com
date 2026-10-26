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
        print(
            f"BGUTIL START ERROR: build/main.js not found: "
            f"{BGUTIL_BUILD}"
        )
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
# COMMON YT-DLP OPTIONS
# =========================================================

def get_common_ydl_opts():

    return {
        "quiet": True,
        "no_warnings": True,

        "noplaylist": True,

        "retries": 3,
        "fragment_retries": 3,

        "socket_timeout": 60,

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


# =========================================================
# SIZE HELPERS
# =========================================================

def format_size(size):

    if not size:
        return None

    try:
        size = float(size)
    except Exception:
        return None

    units = [
        "B",
        "KB",
        "MB",
        "GB",
        "TB"
    ]

    index = 0

    while size >= 1024 and index < len(units) - 1:
        size /= 1024
        index += 1

    if index == 0:
        return f"{int(size)} {units[index]}"

    return f"{size:.1f} {units[index]}"


def get_format_size(fmt):

    if not fmt:
        return None

    # Prefer real filesize
    filesize = fmt.get("filesize")

    if filesize:
        return {
            "bytes": filesize,
            "display": format_size(filesize),
            "approx": False
        }

    # Fallback if extractor only provides approximate size
    filesize_approx = fmt.get("filesize_approx")

    if filesize_approx:
        return {
            "bytes": filesize_approx,
            "display": format_size(filesize_approx),
            "approx": True
        }

    return None


def choose_video_format(formats, max_height):

    candidates = []

    for fmt in formats:

        if fmt.get("vcodec") in (None, "none"):
            continue

        height = fmt.get("height")

        if not height:
            continue

        if height > max_height:
            continue

        candidates.append(fmt)

    if not candidates:
        return None

    # Prefer highest resolution, then bitrate
    candidates.sort(
        key=lambda x: (
            x.get("height") or 0,
            x.get("tbr") or 0
        ),
        reverse=True
    )

    return candidates[0]


def choose_audio_format(formats):

    candidates = []

    for fmt in formats:

        if fmt.get("acodec") in (None, "none"):
            continue

        if fmt.get("vcodec") not in (None, "none"):
            continue

        candidates.append(fmt)

    if not candidates:
        return None

    candidates.sort(
        key=lambda x: (
            x.get("abr") or 0,
            x.get("tbr") or 0
        ),
        reverse=True
    )

    return candidates[0]


def calculate_video_size(info, max_height=None):

    formats = info.get("formats") or []

    video = None
    audio = choose_audio_format(formats)

    if max_height:
        video = choose_video_format(
            formats,
            max_height
        )
    else:
        # Best available video
        video_candidates = [
            f for f in formats
            if f.get("vcodec") not in (None, "none")
            and f.get("height")
        ]

        if video_candidates:
            video_candidates.sort(
                key=lambda x: (
                    x.get("height") or 0,
                    x.get("tbr") or 0
                ),
                reverse=True
            )

            video = video_candidates[0]

    video_size = get_format_size(video)
    audio_size = get_format_size(audio)

    if not video_size and not audio_size:
        return None

    total_bytes = 0
    approximate = False

    if video_size:
        total_bytes += video_size["bytes"]
        approximate = approximate or video_size["approx"]

    if audio_size:
        total_bytes += audio_size["bytes"]
        approximate = approximate or audio_size["approx"]

    return {
        "bytes": total_bytes,
        "display": format_size(total_bytes),
        "approx": approximate
    }


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
# INFO / FILE SIZE
# =========================================================

@app.route("/api/info", methods=["POST", "OPTIONS"])
def info():

    if request.method == "OPTIONS":
        return "", 200

    data = request.get_json(silent=True) or {}

    url = str(
        data.get("url", "")
    ).strip()

    if not url:
        return jsonify({
            "error": "URL is required"
        }), 400

    if not url.startswith(
        ("http://", "https://")
    ):
        return jsonify({
            "error": "Invalid URL"
        }), 400

    print("========================================")
    print("INFO REQUEST")
    print(f"URL: {url}")
    print("========================================")

    try:

        ydl_opts = get_common_ydl_opts()

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:

            info_data = ydl.extract_info(
                url,
                download=False
            )

        title = info_data.get(
            "title",
            "Video"
        )

        duration = info_data.get(
            "duration"
        )

        formats = info_data.get(
            "formats"
        ) or []

        # -----------------------------------------
        # 480p
        # -----------------------------------------

        size_480 = calculate_video_size(
            info_data,
            480
        )

        # -----------------------------------------
        # 720p
        # -----------------------------------------

        size_720 = calculate_video_size(
            info_data,
            720
        )

        # -----------------------------------------
        # 1080p
        # -----------------------------------------

        size_1080 = calculate_video_size(
            info_data,
            1080
        )

        # -----------------------------------------
        # BEST
        # -----------------------------------------

        size_best = calculate_video_size(
            info_data,
            None
        )

        # -----------------------------------------
        # MP3
        # -----------------------------------------
        #
        # MP3 is converted by FFmpeg, so exact final
        # MP3 size is not known before conversion.
        #

        audio_format = choose_audio_format(
            formats
        )

        audio_size = get_format_size(
            audio_format
        )

        result = {
            "title": title,
            "duration": duration,

            "sizes": {
                "480": size_480,
                "720": size_720,
                "1080": size_1080,
                "best": size_best,

                "mp3": {
                    "source": audio_size,
                    "final_exact": False
                }
            }
        }

        print("SIZE INFORMATION:")
        print(result)

        return jsonify(result)

    except Exception as e:

        print("INFO ERROR:")
        print(repr(e))

        return jsonify({
            "error": "Could not get video information",
            "details": str(e)
        }), 500


# =========================================================
# DOWNLOAD
# =========================================================

@app.route("/api/download", methods=["POST", "OPTIONS"])
def download():

    if request.method == "OPTIONS":
        return "", 200

    data = request.get_json(silent=True) or {}

    url = str(
        data.get("url", "")
    ).strip()

    fmt = str(
        data.get("format", "mp4")
    ).lower().strip()

    quality = str(
        data.get("quality", "best")
    ).lower().strip()

    if not url:
        return jsonify({
            "error": "URL is required"
        }), 400

    if not url.startswith(
        ("http://", "https://")
    ):
        return jsonify({
            "error": "Invalid URL"
        }), 400

    job_id = str(uuid.uuid4())

    job_dir = (
        DOWNLOAD_BASE /
        job_id
    )

    job_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    output_template = str(
        job_dir /
        "%(title).120s.%(ext)s"
    )

    # =====================================================
    # FORMAT SELECTION
    # =====================================================

    if fmt == "mp3":

        format_selector = (
            "bestaudio/best"
        )

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
                "base_url": (
                    f"http://127.0.0.1:{BGUTIL_PORT}"
                )
            },
        },

        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/140.0.0.0 Safari/537.36"
            ),
            "Accept-Language": (
                "en-US,en;q=0.9"
            ),
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

        with yt_dlp.YoutubeDL(
            ydl_opts
        ) as ydl:

            info = ydl.extract_info(
                url,
                download=True
            )

            print(
                "Download completed."
            )

        # =================================================
        # FIND OUTPUT FILE
        # =================================================

        files = [
            p for p in job_dir.iterdir()
            if p.is_file()
        ]

        if not files:

            raise RuntimeError(
                "Download completed but output "
                "file was not found."
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

        print(
            f"OUTPUT FILE: {output_file}"
        )

        # =================================================
        # SEND FILE
        # =================================================

        download_name = (
            output_file.name
        )

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

        # Cleanup is intentionally delayed
        # so send_file has enough time to read.
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
