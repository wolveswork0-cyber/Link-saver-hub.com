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
import yt_dlp

app = Flask(__name__)

# IMPORTANT:
# Allow frontend to read Content-Disposition filename header
CORS(
    app,
    expose_headers=["Content-Disposition"]
)

# =========================================================
# DIRECTORIES
# =========================================================

APP_DIR = Path(__file__).resolve().parent
DOWNLOAD_BASE = Path(tempfile.gettempdir()) / "linkdrop_pro"

DOWNLOAD_BASE.mkdir(
    parents=True,
    exist_ok=True
)

# =========================================================
# BGUTIL PO TOKEN SERVER
# =========================================================

BGUTIL_SERVER = (
    APP_DIR
    / "bgutil-ytdlp-pot-provider"
    / "server"
)

BGUTIL_BUILD = (
    BGUTIL_SERVER
    / "build"
    / "main.js"
)

BGUTIL_PORT = 4416

BGUTIL_PROCESS = None


def start_bgutil():

    global BGUTIL_PROCESS

    if not BGUTIL_BUILD.exists():

        print(
            "BGUTIL build not found:",
            BGUTIL_BUILD
        )

        return

    if BGUTIL_PROCESS is not None:

        if BGUTIL_PROCESS.poll() is None:
            return

    node_path = shutil.which("node")

    if not node_path:

        print("Node.js not found.")

        return

    try:

        print(
            "Starting BGUTIL PO Token server..."
        )

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

        def read_logs():

            if BGUTIL_PROCESS is None:
                return

            for line in BGUTIL_PROCESS.stdout:

                print(
                    "[BGUTIL]",
                    line.rstrip()
                )

        threading.Thread(
            target=read_logs,
            daemon=True
        ).start()

        time.sleep(2)

        if BGUTIL_PROCESS.poll() is None:

            print(
                "BGUTIL PO Token server is running "
                f"on 127.0.0.1:{BGUTIL_PORT}"
            )

        else:

            print(
                "BGUTIL PO Token server stopped unexpectedly."
            )

    except Exception as e:

        print(
            "BGUTIL start error:",
            repr(e)
        )


start_bgutil()

# =========================================================
# HELPERS
# =========================================================


def clean_filename(name):

    if not name:
        return "download"

    name = str(name).strip()

    invalid_chars = '<>:"/\\|?*'

    for char in invalid_chars:
        name = name.replace(char, "_")

    name = "".join(
        char
        for char in name
        if ord(char) >= 32
    )

    name = name.replace(
        "\n",
        " "
    ).replace(
        "\r",
        " "
    )

    name = " ".join(
        name.split()
    )

    name = name[:180].strip()

    name = name.rstrip(
        ". "
    )

    if not name:
        return "download"

    return name


def format_size(size):

    if size is None:
        return None

    try:
        size = float(size)
    except Exception:
        return None

    if size <= 0:
        return None

    units = [
        "B",
        "KB",
        "MB",
        "GB",
        "TB"
    ]

    value = size

    for unit in units:

        if value < 1024:

            if unit == "B":
                return f"{int(value)} B"

            return f"{value:.1f} {unit}"

        value /= 1024

    return f"{value:.1f} PB"


def get_format_size(fmt):

    if not fmt:
        return None

    filesize = fmt.get(
        "filesize"
    )

    if filesize:
        return filesize

    filesize_approx = fmt.get(
        "filesize_approx"
    )

    if filesize_approx:
        return filesize_approx

    # If filesize is unavailable,
    # estimate from bitrate × duration.
    tbr = fmt.get("tbr")
    duration = fmt.get("duration")

    if tbr and duration:

        try:

            return (
                float(tbr)
                * 1000
                / 8
                * float(duration)
            )

        except Exception:
            pass

    return None


def get_duration(info):

    try:

        duration = info.get(
            "duration"
        )

        if duration:
            return float(duration)

    except Exception:
        pass

    return None


def get_common_ydl_opts():

    return {

        "quiet": True,

        "no_warnings": True,

        "noplaylist": True,

        "extractor_args": {

            "youtube": {
                "player_client": ["web"]
            },

            "youtubepot-bgutilhttp": {

                "base_url":
                    f"http://127.0.0.1:{BGUTIL_PORT}"

            }
        }
    }


def choose_video_format(height=None):

    if height == 480:

        return (
            "bestvideo[height<=480]+bestaudio/"
            "best[height<=480]/best"
        )

    if height == 720:

        return (
            "bestvideo[height<=720]+bestaudio/"
            "best[height<=720]/best"
        )

    if height == 1080:

        return (
            "bestvideo[height<=1080]+bestaudio/"
            "best[height<=1080]/best"
        )

    return (
        "bestvideo*+bestaudio/best"
    )


def choose_audio_format():

    return "bestaudio/best"


# =========================================================
# SIZE CALCULATION
# =========================================================


def format_matches_height(fmt, height):

    if not fmt:
        return False

    fmt_height = fmt.get(
        "height"
    )

    if not fmt_height:
        return False

    try:

        return int(fmt_height) <= int(height)

    except Exception:

        return False


def get_video_formats(info, height=None):

    formats = (
        info.get("formats")
        or []
    )

    result = []

    for fmt in formats:

        if not fmt:
            continue

        vcodec = fmt.get(
            "vcodec"
        )

        if not vcodec or vcodec == "none":
            continue

        fmt_height = fmt.get(
            "height"
        )

        if not fmt_height:
            continue

        try:
            fmt_height = int(
                fmt_height
            )
        except Exception:
            continue

        if height is not None:

            if fmt_height > height:
                continue

        size = get_format_size(
            fmt
        )

        if size is None:
            continue

        result.append(
            (
                fmt_height,
                size,
                fmt
            )
        )

    return result


def get_audio_formats(info):

    formats = (
        info.get("formats")
        or []
    )

    result = []

    for fmt in formats:

        if not fmt:
            continue

        acodec = fmt.get(
            "acodec"
        )

        if not acodec or acodec == "none":
            continue

        size = get_format_size(
            fmt
        )

        if size is None:
            continue

        abr = fmt.get(
            "abr"
        )

        try:
            abr = float(
                abr or 0
            )
        except Exception:
            abr = 0

        result.append(
            (
                abr,
                size,
                fmt
            )
        )

    return result


def calculate_selected_video_size(
    info,
    height=None
):

    duration = get_duration(
        info
    )

    video_formats = get_video_formats(
        info,
        height
    )

    audio_formats = get_audio_formats(
        info
    )

    if not video_formats:
        return None

    # Highest available video quality
    video_formats.sort(
        key=lambda item: (
            item[0],
            item[1]
        ),
        reverse=True
    )

    selected_video = (
        video_formats[0]
    )

    video_size = (
        selected_video[1]
    )

    audio_size = 0

    if audio_formats:

        audio_formats.sort(
            key=lambda item: (
                item[0],
                item[1]
            ),
            reverse=True
        )

        audio_size = (
            audio_formats[0][1]
        )

    total = (
        video_size
        + audio_size
    )

    return total


def calculate_best_size(info):

    formats = (
        info.get("formats")
        or []
    )

    duration = get_duration(
        info
    )

    best_size = None

    # First try complete formats
    for fmt in formats:

        if not fmt:
            continue

        if (
            fmt.get("vcodec") == "none"
        ):
            continue

        size = get_format_size(
            fmt
        )

        if size is None:
            continue

        if best_size is None:
            best_size = size
        else:
            best_size = max(
                best_size,
                size
            )

    # If separate video/audio streams
    # are available, calculate them.
    separate_size = (
        calculate_selected_video_size(
            info,
            None
        )
    )

    if separate_size:

        if best_size is None:
            best_size = separate_size

        else:
            best_size = max(
                best_size,
                separate_size
            )

    return best_size


def calculate_audio_size(info):

    audio_formats = get_audio_formats(
        info
    )

    if not audio_formats:
        return None

    audio_formats.sort(
        key=lambda item: (
            item[0],
            item[1]
        ),
        reverse=True
    )

    return audio_formats[0][1]


# =========================================================
# BASIC ROUTE
# =========================================================


@app.route(
    "/",
    methods=["GET"]
)
def home():

    return jsonify({

        "name":
            "LinkDrop PRO API",

        "status":
            "online"

    })


# =========================================================
# INFO API
# =========================================================


@app.route(
    "/api/info",
    methods=["POST"]
)
def api_info():

    data = (
        request.get_json(
            silent=True
        )
        or {}
    )

    url = str(
        data.get(
            "url",
            ""
        )
    ).strip()

    if not url:

        return jsonify({

            "success": False,

            "error":
                "URL is required"

        }), 400

    if not (
        url.startswith("http://")
        or
        url.startswith("https://")
    ):

        return jsonify({

            "success": False,

            "error":
                "Invalid URL"

        }), 400

    try:

        opts = get_common_ydl_opts()

        with yt_dlp.YoutubeDL(
            opts
        ) as ydl:

            info = ydl.extract_info(
                url,
                download=False
            )

        title = clean_filename(
            info.get(
                "title"
            )
            or
            "download"
        )

        duration = info.get(
            "duration"
        )

        thumbnail = info.get(
            "thumbnail"
        )

        # -----------------------------
        # CALCULATE SIZES
        # -----------------------------

        size_480 = (
            calculate_selected_video_size(
                info,
                480
            )
        )

        size_720 = (
            calculate_selected_video_size(
                info,
                720
            )
        )

        size_1080 = (
            calculate_selected_video_size(
                info,
                1080
            )
        )

        size_best = (
            calculate_best_size(
                info
            )
        )

        size_mp3 = (
            calculate_audio_size(
                info
            )
        )

        print(
            "INFO TITLE:",
            title
        )

        print(
            "INFO SIZES:",
            {
                "480p":
                    format_size(
                        size_480
                    ),

                "720p":
                    format_size(
                        size_720
                    ),

                "1080p":
                    format_size(
                        size_1080
                    ),

                "best":
                    format_size(
                        size_best
                    ),

                "mp3":
                    format_size(
                        size_mp3
                    )
            }
        )

        return jsonify({

            "success":
                True,

            "title":
                title,

            "duration":
                duration,

            "thumbnail":
                thumbnail,

            "sizes": {

                "480p":
                    format_size(
                        size_480
                    ),

                "720p":
                    format_size(
                        size_720
                    ),

                "1080p":
                    format_size(
                        size_1080
                    ),

                "best":
                    format_size(
                        size_best
                    ),

                "mp3":
                    format_size(
                        size_mp3
                    )
            },

            "sizes_bytes": {

                "480p":
                    size_480,

                "720p":
                    size_720,

                "1080p":
                    size_1080,

                "best":
                    size_best,

                "mp3":
                    size_mp3
            }
        })

    except Exception as e:

        print(
            "INFO ERROR:",
            repr(e)
        )

        return jsonify({

            "success":
                False,

            "error":
                str(e)

        }), 500


# =========================================================
# DOWNLOAD API
# =========================================================


@app.route(
    "/api/download",
    methods=["POST"]
)
def api_download():

    data = (
        request.get_json(
            silent=True
        )
        or {}
    )

    url = str(
        data.get(
            "url",
            ""
        )
    ).strip()

    quality = str(
        data.get(
            "quality",
            "best"
        )
    ).lower()

    if not url:

        return jsonify({

            "success":
                False,

            "error":
                "URL is required"

        }), 400

    if not (
        url.startswith("http://")
        or
        url.startswith("https://")
    ):

        return jsonify({

            "success":
                False,

            "error":
                "Invalid URL"

        }), 400

    # =====================================================
    # TEMP DIRECTORY
    # =====================================================

    job_id = uuid.uuid4().hex

    job_dir = (
        DOWNLOAD_BASE
        / job_id
    )

    job_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    # =====================================================
    # FORMAT
    # =====================================================

    is_audio = quality in (
        "mp3",
        "audio"
    )

    if quality == "480":

        quality = "480p"

    elif quality == "720":

        quality = "720p"

    elif quality == "1080":

        quality = "1080p"

    if quality == "480p":

        format_selector = (
            choose_video_format(480)
        )

    elif quality == "720p":

        format_selector = (
            choose_video_format(720)
        )

    elif quality == "1080p":

        format_selector = (
            choose_video_format(1080)
        )

    elif is_audio:

        format_selector = (
            choose_audio_format()
        )

    else:

        format_selector = (
            choose_video_format(None)
        )

    # =====================================================
    # OUTPUT TEMPLATE
    # =====================================================

    output_template = str(
        job_dir
        / "%(title).180s.%(ext)s"
    )

    opts = get_common_ydl_opts()

    opts.update({

        "format":
            format_selector,

        "outtmpl":
            output_template,

        "restrictfilenames":
            False,

        "windowsfilenames":
            True,

        "merge_output_format":
            "mp4",

        "overwrites":
            True,

    })

    # =====================================================
    # MP3
    # =====================================================

    if is_audio:

        opts.update({

            "format":
                "bestaudio/best",

            "postprocessors": [

                {
                    "key":
                        "FFmpegExtractAudio",

                    "preferredcodec":
                        "mp3",

                    "preferredquality":
                        "192"
                }
            ]
        })

    # =====================================================
    # DOWNLOAD
    # =====================================================

    try:

        with yt_dlp.YoutubeDL(
            opts
        ) as ydl:

            info = ydl.extract_info(
                url,
                download=True
            )

        # =================================================
        # FIND FILE
        # =================================================

        files = [

            p
            for p in job_dir.iterdir()
            if p.is_file()

        ]

        if not files:

            raise RuntimeError(
                "Downloaded file was not found."
            )

        if is_audio:

            mp3_files = [

                p
                for p in files
                if p.suffix.lower()
                == ".mp3"

            ]

            if mp3_files:

                file_path = (
                    mp3_files[0]
                )

            else:

                file_path = files[0]

        else:

            mp4_files = [

                p
                for p in files
                if p.suffix.lower()
                == ".mp4"

            ]

            if mp4_files:

                file_path = (
                    mp4_files[0]
                )

            else:

                file_path = files[0]

        # =================================================
        # ACTUAL TITLE
        # =================================================

        title = clean_filename(
            info.get(
                "title"
            )
            or
            file_path.stem
            or
            "download"
        )

        extension = (
            file_path.suffix
        )

        # =================================================
        # FINAL FILENAME
        # =================================================

        final_name = (
            f"{title}{extension}"
        )

        final_path = (
            job_dir
            / final_name
        )

        if (
            file_path.resolve()
            !=
            final_path.resolve()
        ):

            if final_path.exists():

                final_path.unlink()

            file_path.rename(
                final_path
            )

            file_path = (
                final_path
            )

        print(
            "FINAL DOWNLOAD FILE:",
            file_path.name
        )

        # =================================================
        # SEND FILE
        # =================================================

        response = send_file(

            file_path,

            as_attachment=True,

            download_name=
                file_path.name

        )

        @response.call_on_close
        def cleanup():

            try:

                for item in job_dir.iterdir():

                    try:
                        item.unlink()

                    except Exception:
                        pass

                try:
                    job_dir.rmdir()

                except Exception:
                    pass

            except Exception as e:

                print(
                    "Cleanup error:",
                    repr(e)
                )

        return response

    except Exception as e:

        print(
            "DOWNLOAD ERROR:",
            repr(e)
        )

        try:

            for item in job_dir.iterdir():

                try:
                    item.unlink()

                except Exception:
                    pass

            job_dir.rmdir()

        except Exception:
            pass

        return jsonify({

            "success":
                False,

            "error":
                str(e)

        }), 500


# =========================================================
# HEALTH
# =========================================================


@app.route(
    "/health",
    methods=["GET"]
)
def health():

    bgutil_status = False

    if BGUTIL_PROCESS is not None:

        bgutil_status = (
            BGUTIL_PROCESS.poll()
            is None
        )

    return jsonify({

        "status":
            "ok",

        "bgutil":
            bgutil_status,

        "service":
            "LinkDrop PRO"

    })


# =========================================================
# RUN
# =========================================================


if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            "5000"
        )
    )

    app.run(
        host="0.0.0.0",
        port=port
    )
