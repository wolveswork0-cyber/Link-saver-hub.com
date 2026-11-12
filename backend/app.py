import os
import re
import uuid
import tempfile
import shutil
import socket
import logging
import subprocess
import atexit
import urllib.request
from pathlib import Path
from urllib.parse import urlparse
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from yt_dlp import YoutubeDL

app = Flask(__name__)
CORS(app)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("LinkDropPro")

BASE_DIR = Path(tempfile.gettempdir()) / "linkdrop_pro"
BGUTIL_URL = "http://127.0.0.1:4416"
BGUTIL_DIR = Path(__file__).resolve().parent / "bgutil-ytdlp-pot-provider"
DENO_PATH = Path(__file__).resolve().parent / ".deno" / "bin" / "deno"
BASE_DIR.mkdir(parents=True, exist_ok=True)

# YouTube is intentionally not supported by this website.
YOUTUBE_HOSTS = ("youtube.com", "youtu.be", "youtube-nocookie.com")


def is_youtube_url(url):
    try:
        host = (urlparse(url).hostname or "").lower().rstrip(".")
        return any(host == domain or host.endswith("." + domain)
                   for domain in YOUTUBE_HOSTS)
    except Exception:
        return False


def is_valid_url(url):
    try:
        parsed = urlparse(url)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except Exception:
        return False


def is_snapchat_url(url):
    try:
        host = (urlparse(url).hostname or "").lower()
        return host == "snapchat.com" or host.endswith(".snapchat.com")
    except Exception:
        return False


def format_filesize(size):
    if size is None or size == "":
        return "Size unavailable"
    try:
        size = float(size)
        if size <= 0:
            return "Size unavailable"
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024:
                return f"{size:.2f} {unit}"
            size /= 1024
        return f"{size:.2f} TB"
    except (TypeError, ValueError):
        return "Size unavailable"


def format_duration(seconds):
    if seconds is None:
        return "Unknown"
    seconds = int(seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


class YtDlpLogger:
    def debug(self, message):
        logger.info("[YTDLP] %s", message)

    def warning(self, message):
        logger.warning("[YTDLP] %s", message)

    def error(self, message):
        logger.error("[YTDLP] %s", message)


def make_ydl_options(extra_options=None, source_url=None):
    options = {
        "quiet": True,
        "no_warnings": False,
        "logger": YtDlpLogger(),
        "noplaylist": True,
        "socket_timeout": 30,
        "retries": 3,
        "fragment_retries": 3,
        "format": "best[ext=mp4]/best",
        "extractor_args": {
            "youtubepot-bgutilhttp": {"base_url": BGUTIL_URL},
        },
        "remote_components": ["ejs:npm"],
    }
    if DENO_PATH.exists():
        options["js_runtimes"] = {"deno": {"path": str(DENO_PATH)}}
        logger.info("[DENO] Runtime configured: %s", DENO_PATH)
    else:
        logger.warning("[DENO] Runtime not found")
    if source_url and is_snapchat_url(source_url):
        logger.info("[SNAPCHAT] Default HTTP client enabled")
    if extra_options:
        options.update(extra_options)
    return options


# Start bgutil POT provider locally.
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
            [node_path, str(server_file), "--host", "127.0.0.1", "--port", "4416"],
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
    if bgutil_process and bgutil_process.poll() is None:
        bgutil_process.terminate()


start_bgutil()
atexit.register(stop_bgutil)


def extract_info_with_fallback(url, options):
    try:
        with YoutubeDL(options) as ydl:
            return ydl.extract_info(url, download=False)
    except Exception as primary_error:
        if not is_snapchat_url(url):
            raise
        logger.warning("[SNAPCHAT] Native extractor failed: %s", primary_error)
        logger.warning("[SNAPCHAT] Trying Generic extractor")
        with YoutubeDL(dict(options)) as ydl:
            return ydl.extract_info(url, download=False, ie_key="Generic")


def download_snapchat_generic(url, download_dir):
    logger.info("[SNAPCHAT] Starting Generic extraction")
    options = make_ydl_options(
        {"skip_download": True, "extract_flat": False}, source_url=url
    )
    with YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=False, ie_key="Generic")

    formats = [item for item in info.get("formats", []) if item.get("url")]
    if not formats:
        raise Exception("Snapchat video URL was not found.")
    video_format = max(
        formats,
        key=lambda item: (item.get("height") or 0, item.get("tbr") or 0)
    )
    headers = video_format.get("http_headers") or info.get("http_headers") or {}
    request_headers = {"User-Agent": headers.get("User-Agent", "Mozilla/5.0")}
    for key, value in headers.items():
        if key.lower() not in ("host", "content-length", "connection", "transfer-encoding"):
            request_headers[key] = value

    media_request = urllib.request.Request(video_format["url"], headers=request_headers)
    with urllib.request.urlopen(media_request, timeout=120) as response:
        content_type = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
        first_bytes = response.read(32)
        if len(first_bytes) >= 8 and first_bytes[4:8] == b"ftyp":
            extension = ".mp4"
        elif first_bytes.startswith(b"\x1a\x45\xdf\xa3"):
            extension = ".webm"
        elif content_type == "video/mp4":
            extension = ".mp4"
        elif content_type == "video/webm":
            extension = ".webm"
        elif content_type == "video/quicktime":
            extension = ".mov"
        elif content_type == "video/3gpp":
            extension = ".3gp"
        else:
            raise Exception("Response is not a verified video. Content-Type: " + content_type)

        safe_title = re.sub(r"[^\w\- ]", "", info.get("title") or "snapchat_video").strip()[:100]
        filename = download_dir / ((safe_title or "snapchat_video") + extension)
        with open(filename, "wb") as output_file:
            output_file.write(first_bytes)
            while True:
                chunk = response.read(256 * 1024)
                if not chunk:
                    break
                output_file.write(chunk)
    if not filename.exists() or filename.stat().st_size == 0:
        raise Exception("Snapchat video file is empty.")
    return filename


def build_sizes(info, formats):
    # Use exact filesize where available, otherwise yt-dlp's approximate size.
    video_formats = [
        item for item in formats
        if item.get("height") and item.get("vcodec") != "none"
        and item.get("filesize_value")
    ]
    sizes = {}
    for label, target in (("480p", 480), ("720p", 720), ("1080p", 1080)):
        candidates = [f for f in video_formats if (f.get("height") or 0) <= target]
        if not candidates:
            candidates = video_formats
        if candidates:
            chosen = max(candidates, key=lambda f: (f.get("height") or 0, f.get("tbr") or 0))
            sizes[label] = format_filesize(chosen.get("filesize_value"))
        else:
            sizes[label] = "Size unavailable"

    if video_formats:
        best = max(video_formats, key=lambda f: (f.get("height") or 0, f.get("tbr") or 0))
        sizes["best"] = format_filesize(best.get("filesize_value"))
    else:
        sizes["best"] = format_filesize(info.get("filesize") or info.get("filesize_approx"))

    duration = info.get("duration")
    # MP3 estimate at 192 kbps; this is not an exact server-provided file size.
    sizes["mp3"] = (
        format_filesize((float(duration) * 192000 / 8) if duration else None) + " (approx.)"
        if duration else "Size unavailable"
    )
    return sizes


@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "name": "LinkDrop Pro API",
        "status": "online",
        "message": "Supported public media links only. YouTube is not supported."
    })


@app.route("/health", methods=["GET"])
def health():
    deno_ok = DENO_PATH.exists() and os.access(DENO_PATH, os.X_OK)
    return jsonify({
        "status": "online",
        "deno": deno_ok,
        "deno_path": str(DENO_PATH) if deno_ok else None,
        "bgutil": is_bgutil_running(),
        "node": shutil.which("node") is not None,
    })


@app.route("/api/info", methods=["POST", "OPTIONS"])
def video_info():
    if request.method == "OPTIONS":
        return "", 204
    data = request.get_json(silent=True) or {}
    url = str(data.get("url", "")).strip()
    if not is_valid_url(url):
        return jsonify({"success": False, "error": "Enter a valid video URL."}), 400
    if is_youtube_url(url):
        return jsonify({"success": False, "error": "YouTube links are not supported on LinkDrop Pro."}), 400

    try:
        options = make_ydl_options(
            {"skip_download": True, "extract_flat": False, "verbose": True},
            source_url=url
        )
        info = extract_info_with_fallback(url, options)
        if not info:
            raise Exception("Video information could not be extracted.")

        formats = []
        raw_formats = []
        for item in info.get("formats", []):
            if not item.get("url"):
                continue
            size_value = item.get("filesize") or item.get("filesize_approx")
            raw_formats.append({
                "height": item.get("height"),
                "vcodec": item.get("vcodec"),
                "tbr": item.get("tbr"),
                "filesize_value": size_value,
            })
            formats.append({
                "format_id": item.get("format_id"),
                "ext": item.get("ext"),
                "resolution": item.get("resolution") or (
                    f'{item.get("width")}x{item.get("height")}' if item.get("height") else "Unknown"
                ),
                "filesize": size_value,
                "filesize_text": format_filesize(size_value),
                "format_note": item.get("format_note"),
            })

        return jsonify({
            "success": True,
            "title": info.get("title") or "Video",
            "thumbnail": info.get("thumbnail"),
            "duration": info.get("duration"),
            "duration_string": format_duration(info.get("duration")),
            "uploader": info.get("uploader"),
            "filesize": info.get("filesize") or info.get("filesize_approx"),
            "filesize_text": format_filesize(info.get("filesize") or info.get("filesize_approx")),
            "formats": formats,
            "sizes": build_sizes(info, raw_formats),
        })
    except Exception as error:
        logger.exception("[INFO] Extraction failed")
        return jsonify({"success": False, "error": str(error)[:1000]}), 400


@app.route("/api/download", methods=["POST", "OPTIONS"])
def download_video():
    if request.method == "OPTIONS":
        return "", 204
    data = request.get_json(silent=True) or {}
    url = str(data.get("url", "")).strip()
    if not is_valid_url(url):
        return jsonify({"error": "Enter a valid http/https URL."}), 400
    if is_youtube_url(url):
        return jsonify({"error": "YouTube links are not supported on LinkDrop Pro."}), 400

    download_dir = BASE_DIR / str(uuid.uuid4())
    download_dir.mkdir(parents=True, exist_ok=True)
    try:
        output_template = str(download_dir / "%(title).120s.%(ext)s")
        options = make_ydl_options(
            {"outtmpl": output_template, "noplaylist": True, "overwrites": True, "verbose": True},
            source_url=url
        )
        try:
            with YoutubeDL(options) as ydl:
                ydl.download([url])
        except Exception as primary_error:
            if not is_snapchat_url(url):
                raise
            logger.warning("[SNAPCHAT] Native download failed: %s", primary_error)

        downloaded_files = [
            item for item in download_dir.iterdir()
            if item.is_file() and not item.name.endswith((".part", ".ytdl"))
        ]
        if is_snapchat_url(url) and not downloaded_files:
            for item in download_dir.iterdir():
                if item.is_file():
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item, ignore_errors=True)
            download_snapchat_generic(url, download_dir)
            downloaded_files = [
                item for item in download_dir.iterdir()
                if item.is_file() and not item.name.endswith((".part", ".ytdl"))
            ]
        if not downloaded_files:
            raise Exception("No downloadable media file was created.")

        filename = max(downloaded_files, key=lambda item: item.stat().st_size)
        response = send_file(filename, as_attachment=True, download_name=filename.name)
        response.call_on_close(lambda: shutil.rmtree(download_dir, ignore_errors=True))
        return response
    except Exception as error:
        logger.exception("[DOWNLOAD] Download failed")
        shutil.rmtree(download_dir, ignore_errors=True)
        return jsonify({
            "error": "URL could not be downloaded.",
            "details": str(error)[:1000]
        }), 400


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
