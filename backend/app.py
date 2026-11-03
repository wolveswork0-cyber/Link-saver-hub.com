
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from pathlib import Path
import tempfile
import uuid
import os
import shutil
import subprocess
import threading
import time
import re
import yt_dlp

app = Flask(__name__)
CORS(app, expose_headers=["Content-Disposition"])

# =========================================================
# DIRECTORIES
# =========================================================

APP_DIR = Path(__file__).resolve().parent
DOWNLOAD_BASE = Path(tempfile.gettempdir()) / "linkdrop_pro"
DOWNLOAD_BASE.mkdir(parents=True, exist_ok=True)

# =========================================================
# BGUTIL PO TOKEN SERVER
# =========================================================

BGUTIL_SERVER = APP_DIR / "bgutil-ytdlp-pot-provider" / "server"
BGUTIL_BUILD = BGUTIL_SERVER / "build" / "main.js"
BGUTIL_PORT = int(os.environ.get("BGUTIL_PORT", "4416"))

BGUTIL_PROCESS = None
BGUTIL_LOCK = threading.Lock()


def start_bgutil():
    global BGUTIL_PROCESS

    with BGUTIL_LOCK:
        if BGUTIL_PROCESS is not None and BGUTIL_PROCESS.poll() is None:
            return

        if not BGUTIL_BUILD.is_file():
            print("[BGUTIL] Build file not found:", BGUTIL_BUILD, flush=True)
            return

        node_path = shutil.which("node")

        if not node_path:
            print("[BGUTIL] Node.js not found.", flush=True)
            return

        try:
            print("[BGUTIL] Starting PO Token server...", flush=True)

            proc = subprocess.Popen(
                [
                    node_path,
                    str(BGUTIL_BUILD),
                    "--port", str(BGUTIL_PORT),
                    "--host", "127.0.0.1"
                ],
                cwd=str(BGUTIL_SERVER),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )

            BGUTIL_PROCESS = proc

            def read_logs(process):
                if process.stdout:
                    for line in process.stdout:
                        print("[BGUTIL]", line.rstrip(), flush=True)

            threading.Thread(
                target=read_logs,
                args=(proc,),
                daemon=True
            ).start()

            time.sleep(2)

            if proc.poll() is None:
                print(
                    f"[BGUTIL] Running on 127.0.0.1:{BGUTIL_PORT}",
                    flush=True
                )
            else:
                print(
                    "[BGUTIL] Process exited:",
                    proc.returncode,
                    flush=True
                )

        except Exception as exc:
            print("[BGUTIL START ERROR]", repr(exc), flush=True)


start_bgutil()

# =========================================================
# HELPERS
# =========================================================

def clean_filename(name):
    if not name:
        return "download"

    name = str(name).strip()

    name = re.sub(
        r"^\s*[\d.,]+\s*[KMB]?\s+views?\s*[·•|｜]\s*"
        r"[\d.,]+\s*[KMB]?\s*(?:reactions?|likes?)\s*[|｜]\s*",
        "",
        name,
        flags=re.IGNORECASE
    )

    name = name.split("#", 1)[0].strip()

    for char in '<>:"/\\|?*':
        name = name.replace(char, "_")

    name = "".join(
        char for char in name
        if ord(char) >= 32
    )

    name = " ".join(
        name.replace("\n", " ").replace("\r", " ").split()
    )

    name = name.strip(" .") or "download"

    while len(name.encode("utf-8")) > 150:
        name = name[:-1]

    return name.rstrip(" .") or "download"


def valid_url(url):
    return url.startswith(("https://", "http://"))


def is_youtube(url):
    url = url.lower()
    return "youtube.com/" in url or "youtu.be/" in url


# =========================================================
# YT-DLP OPTIONS
# =========================================================

def get_common_ydl_opts():
    return {
        "quiet": False,
        "no_warnings": False,
        "verbose": True,
        "noplaylist": True,
        "socket_timeout": 30,
        "retries": 3,
        "fragment_retries": 3
    }


def get_ydl_opts(url):
    opts = get_common_ydl_opts()

    if is_youtube(url):
        opts["extractor_args"] = {
            "youtube": {
                "player_client": ["mweb"]
            },
            "youtubepot-bgutilhttp": {
                "base_url": f"http://127.0.0.1:{BGUTIL_PORT}"
            }
        }

    return opts


# =========================================================
# FORMAT SELECTION
# =========================================================

def choose_video_format(height=None):
    if height in (480, 720, 1080):
        return (
            f"bestvideo[height<={height}]+bestaudio/"
            f"best[height<={height}]/best"
        )

    return "bestvideo*+bestaudio/best"


def choose_audio_format():
    return "bestaudio/best"


def get_quality(data):
    quality = str(
        data.get("quality", "best")
    ).lower().strip()

    quality = {
        "480": "480p",
        "720": "720p",
        "1080": "1080p"
    }.get(quality, quality)

    is_audio = quality in ("mp3", "audio")

    if is_audio:
        selector = choose_audio_format()
    elif quality == "480p":
        selector = choose_video_format(480)
    elif quality == "720p":
        selector = choose_video_format(720)
    elif quality == "1080p":
        selector = choose_video_format(1080)
    else:
        selector = choose_video_format()

    return selector, is_audio


# =========================================================
# SIZE HELPERS
# =========================================================

def format_size(size, approximate=False):
    if size is None:
        return None

    try:
        value = float(size)
    except (TypeError, ValueError):
        return None

    if value <= 0:
        return None

    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024:
            result = (
                f"{int(value)} B"
                if unit == "B"
                else f"{value:.1f} {unit}"
            )
            return "~" + result if approximate else result

        value /= 1024

    result = f"{value:.1f} PB"
    return "~" + result if approximate else result


def get_duration(info):
    try:
        duration = info.get("duration")
        return float(duration) if duration else None
    except (TypeError, ValueError):
        return None


def get_format_size(fmt):
    if not fmt:
        return None, False

    for key, approximate in (
        ("filesize", False),
        ("filesize_approx", True)
    ):
        value = fmt.get(key)

        if value:
            try:
                return float(value), approximate
            except (TypeError, ValueError):
                pass

    tbr = fmt.get("tbr")
    duration = fmt.get("duration")

    if tbr and duration:
        try:
            size = float(tbr) * 1000 * float(duration) / 8

            if size > 0:
                return size, True

        except (TypeError, ValueError):
            pass

    return None, False


def get_video_formats(info, max_height=None):
    result = []

    for fmt in info.get("formats") or []:
        if not fmt or fmt.get("vcodec") in (None, "none"):
            continue

        try:
            height = int(fmt.get("height") or 0)
        except (TypeError, ValueError):
            continue

        if not height:
            continue

        if max_height is not None and height > max_height:
            continue

        size, approximate = get_format_size(fmt)

        result.append({
            "height": height,
            "size": size,
            "approximate": approximate
        })

    return result


def get_audio_formats(info):
    result = []

    for fmt in info.get("formats") or []:
        if not fmt or fmt.get("acodec") in (None, "none"):
            continue

        size, approximate = get_format_size(fmt)

        if size is None:
            continue

        try:
            abr = float(fmt.get("abr") or 0)
        except (TypeError, ValueError):
            abr = 0

        result.append({
            "abr": abr,
            "size": size,
            "approximate": approximate
        })

    return result


def fallback_video_bitrate(height):
    if height <= 480:
        return 1500000
    if height <= 720:
        return 3000000
    if height <= 1080:
        return 5000000
    return 8000000


def estimate_video_size(info, max_height):
    duration = get_duration(info)
    formats = get_video_formats(info, max_height)

    if not duration or not formats:
        return None, True

    formats.sort(
        key=lambda x: (x["height"], x["size"] or 0),
        reverse=True
    )

    video = formats[0]
    size = video["size"]
    approximate = video["approximate"]

    if size is None:
        size = fallback_video_bitrate(video["height"]) * duration / 8
        approximate = True

    audios = get_audio_formats(info)

    if audios:
        audios.sort(
            key=lambda x: (x["abr"], x["size"]),
            reverse=True
        )

        audio = audios[0]
        size += audio["size"]
        approximate = approximate or audio["approximate"]

    else:
        size += 128000 * duration / 8
        approximate = True

    return size, approximate


def calculate_best_size(info):
    duration = get_duration(info)
    formats = get_video_formats(info)

    if not formats:
        return None, True

    formats.sort(
        key=lambda x: (x["height"], x["size"] or 0),
        reverse=True
    )

    video = formats[0]
    size = video["size"]
    approximate = video["approximate"]

    if size is None:
        if not duration:
            return None, True

        size = fallback_video_bitrate(video["height"]) * duration / 8
        approximate = True

    audios = get_audio_formats(info)

    if audios:
        audios.sort(
            key=lambda x: (x["abr"], x["size"]),
            reverse=True
        )

        audio = audios[0]
        size += audio["size"]
        approximate = approximate or audio["approximate"]

    elif duration:
        size += 128000 * duration / 8
        approximate = True

    return size, approximate


def calculate_audio_size(info):
    audios = get_audio_formats(info)

    if not audios:
        return None, True

    audios.sort(
        key=lambda x: (x["abr"], x["size"]),
        reverse=True
    )

    return audios[0]["size"], audios[0]["approximate"]


# =========================================================
# HOME
# =========================================================

@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "name": "LinkDrop PRO API",
        "status": "online"
    })


# =========================================================
# INFO API
# =========================================================

@app.route("/api/info", methods=["POST"])
def api_info():
    data = request.get_json(silent=True) or {}
    url = str(data.get("url", "")).strip()

    if not url:
        return jsonify({
            "success": False,
            "error": "URL is required"
        }), 400

    if not valid_url(url):
        return jsonify({
            "success": False,
            "error": "Invalid URL"
        }), 400

    try:
        opts = get_ydl_opts(url)

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(
                url,
                download=False
            )

        if not info:
            raise RuntimeError("No video information returned.")

        if info.get("_type") in ("playlist", "multi_video"):
            entries = [
                entry for entry in (info.get("entries") or [])
                if entry
            ]

            if not entries:
                raise RuntimeError("No playable video found.")

            info = entries[0]

        sizes = {}
        sizes_bytes = {}

        for key, height in (
            ("480p", 480),
            ("720p", 720),
            ("1080p", 1080)
        ):
            size, approx = estimate_video_size(info, height)

            sizes[key] = format_size(size, approx)
            sizes_bytes[key] = size

        best_size, best_approx = calculate_best_size(info)
        mp3_size, mp3_approx = calculate_audio_size(info)

        sizes["best"] = format_size(best_size, best_approx)
        sizes["mp3"] = format_size(mp3_size, mp3_approx)

        sizes_bytes["best"] = best_size
        sizes_bytes["mp3"] = mp3_size

        title = clean_filename(
            info.get("title") or "download"
        )

        print("[INFO SUCCESS]", title, flush=True)

        return jsonify({
            "success": True,
            "title": title,
            "duration": info.get("duration"),
            "thumbnail": info.get("thumbnail"),
            "sizes": sizes,
            "sizes_bytes": sizes_bytes
        })

    except Exception as exc:
        print(
            "[INFO ERROR]",
            type(exc).__name__,
            repr(exc),
            flush=True
        )

        return jsonify({
            "success": False,
            "error": str(exc)
        }), 500


# =========================================================
# DOWNLOAD API
# =========================================================

@app.route("/api/download", methods=["POST"])
def api_download():
    data = request.get_json(silent=True) or {}
    url = str(data.get("url", "")).strip()

    if not url:
        return jsonify({
            "success": False,
            "error": "URL is required"
        }), 400

    if not valid_url(url):
        return jsonify({
            "success": False,
            "error": "Invalid URL"
        }), 400

    format_selector, is_audio = get_quality(data)

    job_dir = DOWNLOAD_BASE / uuid.uuid4().hex
    job_dir.mkdir(parents=True, exist_ok=True)

    opts = get_ydl_opts(url)

    opts.update({
        "format": format_selector,
        "outtmpl": str(job_dir / "%(id)s.%(ext)s"),
        "windowsfilenames": True,
        "overwrites": True
    })

    if is_audio:
        opts.update({
            "format": "bestaudio/best",
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192"
            }]
        })

    else:
        # yt-dlp merges separate video/audio streams to MP4.
        # A single-file source keeps its native extension.
        opts["merge_output_format"] = "mp4"

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(
                url,
                download=True
            )

        if not info:
            raise RuntimeError("No video information returned.")

        if info.get("_type") in ("playlist", "multi_video"):
            entries = [
                entry for entry in (info.get("entries") or [])
                if entry
            ]

            if entries:
                info = entries[0]

        downloaded_files = [
            path for path in job_dir.iterdir()
            if path.is_file()
        ]

        if not downloaded_files:
            raise RuntimeError("Downloaded file was not found.")

        if is_audio:
            candidates = [
                path for path in downloaded_files
                if path.suffix.lower() == ".mp3"
            ]
        else:
            candidates = [
                path for path in downloaded_files
                if path.suffix.lower() in (
                    ".mp4", ".mkv", ".webm",
                    ".mov", ".m4v"
                )
            ]

        file_path = max(
            candidates or downloaded_files,
            key=lambda path: path.stat().st_size
        )

        title = clean_filename(
            info.get("title") or file_path.stem
        )

        final_path = job_dir / (
            title + file_path.suffix.lower()
        )

        if file_path.resolve() != final_path.resolve():
            if final_path.exists():
                final_path.unlink()

            file_path.rename(final_path)
            file_path = final_path

        print(
            "[DOWNLOAD COMPLETE]",
            file_path.name,
            flush=True
        )

        response = send_file(
            file_path,
            as_attachment=True,
            download_name=file_path.name
        )

        @response.call_on_close
        def cleanup():
            shutil.rmtree(
                job_dir,
                ignore_errors=True
            )

        return response

    except Exception as exc:
        print(
            "[DOWNLOAD ERROR]",
            type(exc).__name__,
            repr(exc),
            flush=True
        )

        shutil.rmtree(
            job_dir,
            ignore_errors=True
        )

        return jsonify({
            "success": False,
            "error": str(exc)
        }), 500


# =========================================================
# HEALTH CHECK
# =========================================================

@app.route("/health", methods=["GET"])
def health():
    running = (
        BGUTIL_PROCESS is not None
        and BGUTIL_PROCESS.poll() is None
    )

    return jsonify({
        "status": "ok",
        "bgutil_process_running": running,
        "bgutil_port": BGUTIL_PORT,
        "yt_dlp_version": yt_dlp.version.__version__,
        "service": "LinkDrop PRO"
    })


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))

    app.run(
        host="0.0.0.0",
        port=port
    )
