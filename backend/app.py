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

CORS(
    app,
    expose_headers=["Content-Disposition"]
)

# =========================================================
# DIRECTORIES
# =========================================================

APP_DIR = Path(__file__).resolve().parent

DOWNLOAD_BASE = (
    Path(tempfile.gettempdir())
    / "linkdrop_pro"
)

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
        name = name.replace(
            char,
            "_"
        )

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


def format_size(size, approximate=False):

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

                text = (
                    f"{int(value)} B"
                )

            else:

                text = (
                    f"{value:.1f} {unit}"
                )

            if approximate:
                return "~" + text

            return text

        value /= 1024

    text = f"{value:.1f} PB"

    if approximate:
        return "~" + text

    return text


def get_duration(info):

    try:

        duration = info.get(
            "duration"
        )

        if duration:

            return float(
                duration
            )

    except Exception:
        pass

    return None


def get_format_size(fmt):

    if not fmt:
        return None, False

    # ---------------------------------------------
    # Exact filesize
    # ---------------------------------------------

    filesize = fmt.get(
        "filesize"
    )

    if filesize:

        try:

            return (
                float(filesize),
                False
            )

        except Exception:
            pass

    # ---------------------------------------------
    # Approximate filesize from yt-dlp
    # ---------------------------------------------

    filesize_approx = fmt.get(
        "filesize_approx"
    )

    if filesize_approx:

        try:

            return (
                float(filesize_approx),
                True
            )

        except Exception:
            pass

    # ---------------------------------------------
    # Calculate from bitrate × duration
    # ---------------------------------------------

    tbr = fmt.get(
        "tbr"
    )

    duration = fmt.get(
        "duration"
    )

    if tbr and duration:

        try:

            size = (
                float(tbr)
                * 1000
                * float(duration)
                / 8
            )

            if size > 0:

                return (
                    size,
                    True
                )

        except Exception:
            pass

    return (
        None,
        False
    )


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

        if not acodec:
            continue

        if acodec == "none":
            continue

        size, approximate = (
            get_format_size(fmt)
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
            {
                "abr": abr,
                "size": size,
                "approximate": approximate,
                "format": fmt
            }
        )

    return result


def get_video_formats(
    info,
    max_height=None
):

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

        if not vcodec:
            continue

        if vcodec == "none":
            continue

        height = fmt.get(
            "height"
        )

        if not height:
            continue

        try:

            height = int(
                height
            )

        except Exception:

            continue

        if max_height is not None:

            if height > max_height:
                continue

        size, approximate = (
            get_format_size(fmt)
        )

        result.append(
            {
                "height": height,
                "size": size,
                "approximate": approximate,
                "format": fmt
            }
        )

    return result


# =========================================================
# FALLBACK VIDEO BITRATES
# =========================================================

def fallback_bitrate(height):

    # Approximate total video bitrate.
    #
    # These are only used when yt-dlp does not provide
    # filesize or bitrate information.

    if height <= 480:

        return 1500 * 1000

    if height <= 720:

        return 3000 * 1000

    if height <= 1080:

        return 5000 * 1000

    return 8000 * 1000


def estimate_video_size(
    info,
    target_height
):

    duration = get_duration(
        info
    )

    if not duration:
        return None, True

    video_formats = get_video_formats(
        info,
        target_height
    )

    if not video_formats:
        return None, True

    # ---------------------------------------------
    # Pick highest available video quality
    # under requested resolution
    # ---------------------------------------------

    video_formats.sort(
        key=lambda item: (
            item["height"],
            item["size"] or 0
        ),
        reverse=True
    )

    selected = (
        video_formats[0]
    )

    video_size = (
        selected["size"]
    )

    approximate = (
        selected["approximate"]
    )

    # ---------------------------------------------
    # If actual/approximate filesize exists
    # ---------------------------------------------

    if video_size is not None:

        total = video_size

    else:

        bitrate = fallback_bitrate(
            selected["height"]
        )

        total = (
            bitrate
            * duration
            / 8
        )

        approximate = True

    # ---------------------------------------------
    # Add best available audio
    # ---------------------------------------------

    audio_formats = get_audio_formats(
        info
    )

    if audio_formats:

        audio_formats.sort(
            key=lambda item: (
                item["abr"],
                item["size"]
            ),
            reverse=True
        )

        audio = (
            audio_formats[0]
        )

        if audio["size"] is not None:

            total += audio["size"]

            if audio["approximate"]:
                approximate = True

        else:

            # Typical audio fallback
            audio_bitrate = (
                128 * 1000
            )

            total += (
                audio_bitrate
                * duration
                / 8
            )

            approximate = True

    else:

        # Audio unavailable in metadata,
        # use conservative fallback.
        audio_bitrate = (
            128 * 1000
        )

        total += (
            audio_bitrate
            * duration
            / 8
        )

        approximate = True

    return (
        total,
        approximate
    )


def calculate_best_size(info):

    formats = (
        info.get("formats")
        or []
    )

    best_size = None
    approximate = False

    # ---------------------------------------------
    # Complete video+audio formats
    # ---------------------------------------------

    for fmt in formats:

        if not fmt:
            continue

        vcodec = fmt.get(
            "vcodec"
        )

        if not vcodec:
            continue

        if vcodec == "none":
            continue

        acodec = fmt.get(
            "acodec"
        )

        if not acodec:
            continue

        if acodec == "none":
            continue

        size, is_approx = (
            get_format_size(fmt)
        )

        if size is None:
            continue

        if (
            best_size is None
            or
            size > best_size
        ):

            best_size = size
            approximate = is_approx

    # ---------------------------------------------
    # Separate video + audio
    # ---------------------------------------------

    video_formats = get_video_formats(
        info,
        None
    )

    audio_formats = get_audio_formats(
        info
    )

    if video_formats:

        video_formats.sort(
            key=lambda item: (
                item["height"],
                item["size"] or 0
            ),
            reverse=True
        )

        video = (
            video_formats[0]
        )

        video_size = (
            video["size"]
        )

        video_approx = (
            video["approximate"]
        )

        if video_size is None:

            duration = get_duration(
                info
            )

            if duration:

                bitrate = fallback_bitrate(
                    video["height"]
                )

                video_size = (
                    bitrate
                    * duration
                    / 8
                )

                video_approx = True

        audio_size = 0
        audio_approx = False

        if audio_formats:

            audio_formats.sort(
                key=lambda item: (
                    item["abr"],
                    item["size"]
                ),
                reverse=True
            )

            audio = (
                audio_formats[0]
            )

            if audio["size"] is not None:

                audio_size = (
                    audio["size"]
                )

                audio_approx = (
                    audio["approximate"]
                )

            else:

                duration = get_duration(
                    info
                )

                if duration:

                    audio_size = (
                        128
                        * 1000
                        * duration
                        / 8
                    )

                    audio_approx = True

        if video_size is not None:

            combined = (
                video_size
                + audio_size
            )

            if (
                best_size is None
                or
                combined > best_size
            ):

                best_size = combined

                approximate = (
                    video_approx
                    or
                    audio_approx
                )

    return (
        best_size,
        approximate
    )


def calculate_audio_size(info):

    audio_formats = get_audio_formats(
        info
    )

    if not audio_formats:
        return None, True

    audio_formats.sort(
        key=lambda item: (
            item["abr"],
            item["size"]
        ),
        reverse=True
    )

    selected = (
        audio_formats[0]
    )

    return (
        selected["size"],
        selected["approximate"]
    )


# =========================================================
# COMMON YT-DLP OPTIONS
# =========================================================

def get_common_ydl_opts():

    return {

        "quiet": True,

        "no_warnings": True,

        "noplaylist": True,

        "extractor_args": {

            "youtube": {

                "player_client": [
                    "web"
                ]

            },

            "youtubepot-bgutilhttp": {

                "base_url":
                    f"http://127.0.0.1:{BGUTIL_PORT}"

            }

        }

    }


def choose_video_format(
    height=None
):

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
# HOME
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

        # ---------------------------------------------
        # RESOLUTION SIZES
        # ---------------------------------------------

        size_480, approx_480 = (
            estimate_video_size(
                info,
                480
            )
        )

        size_720, approx_720 = (
            estimate_video_size(
                info,
                720
            )
        )

        size_1080, approx_1080 = (
            estimate_video_size(
                info,
                1080
            )
        )

        size_best, approx_best = (
            calculate_best_size(
                info
            )
        )

        size_mp3, approx_mp3 = (
            calculate_audio_size(
                info
            )
        )

        sizes = {

            "480p":
                format_size(
                    size_480,
                    approx_480
                ),

            "720p":
                format_size(
                    size_720,
                    approx_720
                ),

            "1080p":
                format_size(
                    size_1080,
                    approx_1080
                ),

            "best":
                format_size(
                    size_best,
                    approx_best
                ),

            "mp3":
                format_size(
                    size_mp3,
                    approx_mp3
                )

        }

        sizes_bytes = {

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

        print(
            "INFO TITLE:",
            title
        )

        print(
            "INFO SIZES:",
            sizes
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

            "sizes":
                sizes,

            "sizes_bytes":
                sizes_bytes

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
    # JOB DIRECTORY
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
            choose_video_format(
                480
            )
        )

    elif quality == "720p":

        format_selector = (
            choose_video_format(
                720
            )
        )

    elif quality == "1080p":

        format_selector = (
            choose_video_format(
                1080
            )
        )

    elif is_audio:

        format_selector = (
            choose_audio_format()
        )

    else:

        format_selector = (
            choose_video_format()
        )

    # =====================================================
    # OUTPUT
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
            True

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
        # REAL TITLE
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
        # SEND
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
