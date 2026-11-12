
const form = document.querySelector("#form");
const input = document.querySelector("#url");
const msg = document.querySelector("#msg");
const list = document.querySelector("#list");
const theme = document.querySelector("#theme");

const API_BASE = "https://linkdrop-pro-3clf.onrender.com";
const API_DOWNLOAD = `${API_BASE}/api/download`;
const API_INFO = `${API_BASE}/api/info`;

let history = [];
try {
    history = JSON.parse(localStorage.getItem("linkdrop-history") || "[]");
    if (!Array.isArray(history)) history = [];
} catch (error) {
    history = [];
}

// YouTube links are not supported.
function isYouTubeUrl(value) {
    try {
        const host = new URL(value).hostname.toLowerCase().replace(/\.$/, "");
        return ["youtube.com", "youtu.be", "youtube-nocookie.com"]
            .some(domain => host === domain || host.endsWith("." + domain));
    } catch (error) {
        return false;
    }
}

function escapeHtml(value) {
    return String(value)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

function render() {
    if (!list) return;
    list.innerHTML = history.length
        ? history.map((url, index) => `
            <li class="item">
                <a href="${escapeHtml(url)}" target="_blank" rel="noopener">${escapeHtml(url)}</a>
                <button type="button" data-remove="${index}" aria-label="Remove link">×</button>
            </li>
        `).join("")
        : '<li class="empty-history">No downloads yet.</li>';
}

if (list) {
    list.addEventListener("click", event => {
        const button = event.target.closest("[data-remove]");
        if (!button) return;
        history.splice(Number(button.dataset.remove), 1);
        localStorage.setItem("linkdrop-history", JSON.stringify(history));
        render();
    });
}

const clearButton = document.querySelector("#clear");
if (clearButton) {
    clearButton.addEventListener("click", () => {
        history = [];
        localStorage.removeItem("linkdrop-history");
        render();
    });
}

function displaySize(size) {
    if (size === null || size === undefined || size === "") {
        return "Size unavailable";
    }
    return String(size);
}

function cleanFilename(name) {
    if (!name) return "download";
    let safe = String(name).trim()
        .replace(/[<>:"/\\|?*\x00-\x1F]/g, "_")
        .replace(/[. ]+$/g, "")
        .replace(/\s+/g, " ")
        .substring(0, 180)
        .trim();
    return safe || "download";
}

async function getVideoInfo(url) {
    const response = await fetch(API_INFO, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({url})
    });

    let data = null;
    try {
        data = await response.json();
    } catch (error) {}

    if (!response.ok || !data || !data.success) {
        throw new Error(data?.error || "Could not read video information.");
    }
    return data;
}

async function showOptions(url) {
    document.querySelector("#download-options")?.remove();
    if (msg) msg.textContent = "Checking available formats...";

    let videoInfo;
    try {
        videoInfo = await getVideoInfo(url);
    } catch (error) {
        if (msg) msg.textContent = "Could not check video formats: " + error.message;
        return;
    }

    const sizes = videoInfo.sizes || {};
    const videoTitle = cleanFilename(videoInfo.title || "download");
    const box = document.createElement("div");
    box.id = "download-options";

    const choices = [
        {format:"mp4", quality:"480p", title:"MP4 — 480p", detail:"Standard quality", size:sizes["480p"], cls:"option-blue", icon:"▶"},
        {format:"mp4", quality:"720p", title:"MP4 — 720p", detail:"HD quality", size:sizes["720p"], cls:"option-purple", icon:"▶"},
        {format:"mp4", quality:"1080p", title:"MP4 — 1080p", detail:"Full HD quality", size:sizes["1080p"], cls:"option-green", icon:"▶"},
        {format:"mp4", quality:"best", title:"MP4 — Best Quality", detail:"Highest available quality", size:sizes["best"], cls:"option-gold", icon:"★"},
        {format:"mp3", quality:"audio", title:"MP3 — Audio", detail:"192 kbps MP3 (estimated size)", size:sizes["mp3"], cls:"option-pink", icon:"♪"}
    ];

    box.innerHTML = `
      <div class="download-options-inner">
        <div class="options-header">
          <div class="options-icon">↓</div>
          <div><h3>Select Download Format</h3><p>${escapeHtml(videoTitle)}</p></div>
        </div>
        <div class="download-option-list">
          ${choices.map(item => `
            <button type="button" class="download-option ${item.cls}"
              data-format="${item.format}" data-quality="${item.quality}">
              <span class="option-icon">${item.icon}</span>
              <span class="option-text"><strong>${item.title}</strong><small>${item.detail}</small></span>
              <span class="option-size">${escapeHtml(displaySize(item.size))}</span>
              <span class="option-arrow">›</span>
            </button>
          `).join("")}
        </div>
        <button type="button" id="cancel-download" class="cancel-download">Cancel</button>
      </div>`;

    form.parentNode.insertBefore(box, form.nextSibling);

    box.querySelectorAll("button[data-format]").forEach(button => {
        button.addEventListener("click", () => {
            const format = button.dataset.format;
            const quality = button.dataset.quality;
            box.remove();
            startDownload(url, format, quality, videoTitle);
        });
    });

    box.querySelector("#cancel-download").addEventListener("click", () => {
        box.remove();
        if (msg) msg.textContent = "Download cancelled.";
    });

    if (msg) msg.textContent = "Choose your download format.";
}

async function startDownload(url, format, quality, videoTitle) {
    if (!url) {
        if (msg) msg.textContent = "Please enter a valid video URL.";
        return;
    }
    if (isYouTubeUrl(url)) {
        if (msg) msg.textContent = "YouTube links are not supported on LinkDrop Pro.";
        return;
    }

    if (msg) msg.textContent = "Preparing your download...";
    const submitButton = form?.querySelector('button[type="submit"]');
    const oldButtonText = submitButton?.innerText || "";

    if (submitButton) {
        submitButton.disabled = true;
        submitButton.innerText = "Downloading...";
    }

    try {
        const response = await fetch(API_DOWNLOAD, {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({url, format, quality})
        });

        if (!response.ok) {
            let errorText = "Download failed.";
            try {
                const errorData = await response.json();
                errorText = errorData.error || errorData.details || errorText;
            } catch (error) {}
            throw new Error(errorText);
        }

        const blob = await response.blob();
        if (!blob || blob.size === 0) {
            throw new Error("Empty file received.");
        }

        let filename = "";
        const disposition = response.headers.get("Content-Disposition") || "";
        const utfMatch = disposition.match(/filename\*=UTF-8''([^;]+)/i);

        if (utfMatch) {
            try {
                filename = decodeURIComponent(utfMatch[1]);
            } catch (error) {}
        }

        if (!filename) {
            const normalMatch = disposition.match(/filename="?([^"]+)"?/i);
            if (normalMatch) filename = normalMatch[1];
        }

        if (!filename) filename = cleanFilename(videoTitle || "download");

        const downloadURL = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = downloadURL;
        link.download = filename;
        link.style.display = "none";
        document.body.appendChild(link);
        link.click();
        link.remove();

        setTimeout(() => URL.revokeObjectURL(downloadURL), 10000);

        history = [url, ...history.filter(item => item !== url)].slice(0, 10);
        localStorage.setItem("linkdrop-history", JSON.stringify(history));
        render();

        if (msg) msg.textContent = `Download completed: ${filename}`;
        input.value = "";
    } catch (error) {
        console.error("Download error:", error);
        if (msg) msg.textContent = "Download failed: " + error.message;
    } finally {
        if (submitButton) {
            submitButton.disabled = false;
            submitButton.innerText = oldButtonText || "↓ Download Now";
        }
    }
}

if (form) {
    form.addEventListener("submit", async event => {
        event.preventDefault();
        const url = input.value.trim();

        if (!url) {
            if (msg) msg.textContent = "Please paste a video URL.";
            return;
        }

        try {
            const parsed = new URL(url);

            if (!["http:", "https:"].includes(parsed.protocol)) {
                throw new Error("Invalid URL");
            }

            if (isYouTubeUrl(url)) {
                if (msg) msg.textContent = "YouTube links are not supported on LinkDrop Pro.";
                return;
            }

            await showOptions(url);
        } catch (error) {
            if (msg) msg.textContent = "Please enter a valid HTTP/HTTPS link.";
        }
    });
}

if (theme) {
    theme.addEventListener("click", () => {
        document.body.classList.toggle("dark");
    });
}

render();
