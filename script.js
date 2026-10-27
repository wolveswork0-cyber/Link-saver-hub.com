const form = document.querySelector("#form");
const input = document.querySelector("#url");
const msg = document.querySelector("#msg");
const list = document.querySelector("#list");
const theme = document.querySelector("#theme");

const API_BASE = "https://linkdrop-pro-3clf.onrender.com";
const API_DOWNLOAD = `${API_BASE}/api/download`;
const API_INFO = `${API_BASE}/api/info`;

let history = JSON.parse(
    localStorage.getItem("linkdrop-history") || "[]"
);


// =========================
// HISTORY
// =========================

function render() {
    if (!list) return;

    list.innerHTML = history.length
        ? history.map((url, index) => `
            <div class="item">
                <a href="${url}" target="_blank" rel="noopener">
                    ${url}
                </a>

                <button
                    type="button"
                    onclick="removeItem(${index})">
                    ×
                </button>
            </div>
        `).join("")
        : '<p class="empty">No downloads yet.</p>';
}


function removeItem(index) {
    history.splice(index, 1);

    localStorage.setItem(
        "linkdrop-history",
        JSON.stringify(history)
    );

    render();
}


const clearButton = document.querySelector("#clear");

if (clearButton) {
    clearButton.addEventListener("click", () => {

        history = [];

        localStorage.removeItem("linkdrop-history");

        render();
    });
}


// =========================
// SIZE DISPLAY
// =========================

function displaySize(size) {

    if (!size) {
        return "Size unavailable";
    }

    if (typeof size === "string") {
        return size;
    }

    if (size.display) {
        return size.approx
            ? `~${size.display}`
            : size.display;
    }

    return "Size unavailable";
}


// =========================
// CLEAN FILENAME
// =========================

function cleanFilename(name) {

    if (!name) {
        return "download";
    }

    name = String(name).trim();

    // Remove invalid filename characters
    name = name.replace(/[<>:"/\\|?*\x00-\x1F]/g, "_");

    // Remove trailing dots/spaces
    name = name.replace(/[. ]+$/g, "");

    // Limit filename length
    name = name.substring(0, 180).trim();

    if (!name) {
        return "download";
    }

    return name;
}


// =========================
// GET VIDEO INFORMATION
// =========================

async function getVideoInfo(url) {

    const response = await fetch(
        API_INFO,
        {
            method: "POST",

            headers: {
                "Content-Type": "application/json"
            },

            body: JSON.stringify({
                url: url
            })
        }
    );


    if (!response.ok) {

        let errorMessage =
            "Could not read video information.";

        try {

            const data =
                await response.json();

            if (data.details) {
                errorMessage = data.details;
            } else if (data.error) {
                errorMessage = data.error;
            }

        } catch (e) {}

        throw new Error(errorMessage);
    }


    const data =
        await response.json();


    if (!data.success) {

        throw new Error(
            data.error ||
            "Could not read video information."
        );
    }


    return data;
}


// =========================
// DOWNLOAD OPTIONS
// =========================

async function showOptions(url) {

    const oldBox =
        document.querySelector(
            "#download-options"
        );


    if (oldBox) {
        oldBox.remove();
    }


    if (msg) {
        msg.textContent =
            "Checking available formats...";
    }


    let videoInfo;


    try {

        videoInfo =
            await getVideoInfo(url);

    } catch (error) {

        console.error(
            "Info error:",
            error
        );


        if (msg) {

            msg.textContent =
                "Could not check video formats. Please try again.";
        }

        return;
    }


    const sizes =
        videoInfo.sizes || {};


    const videoTitle =
        cleanFilename(
            videoInfo.title ||
            "download"
        );


    const box =
        document.createElement("div");


    box.id =
        "download-options";


    box.innerHTML = `
        <div class="download-options-inner">

            <div class="options-header">

                <div class="options-icon">
                    ↓
                </div>

                <div>
                    <h3>
                        Select Download Format
                    </h3>

                    <p>
                        ${escapeHtml(videoTitle)}
                    </p>
                </div>

            </div>


            <div class="download-option-list">

                <button
                    type="button"
                    class="download-option option-blue"
                    data-format="mp4"
                    data-quality="480">

                    <span class="option-icon">
                        ▶
                    </span>

                    <span class="option-text">

                        <strong>
                            MP4 — 480p
                        </strong>

                        <small>
                            Standard quality
                        </small>

                    </span>

                    <span class="option-size">
                        ${displaySize(sizes["480"])}
                    </span>

                    <span class="option-arrow">
                        ›
                    </span>

                </button>


                <button
                    type="button"
                    class="download-option option-purple"
                    data-format="mp4"
                    data-quality="720">

                    <span class="option-icon">
                        ▶
                    </span>

                    <span class="option-text">

                        <strong>
                            MP4 — 720p
                        </strong>

                        <small>
                            HD quality
                        </small>

                    </span>

                    <span class="option-size">
                        ${displaySize(sizes["720"])}
                    </span>

                    <span class="option-arrow">
                        ›
                    </span>

                </button>


                <button
                    type="button"
                    class="download-option option-green"
                    data-format="mp4"
                    data-quality="1080">

                    <span class="option-icon">
                        ▶
                    </span>

                    <span class="option-text">

                        <strong>
                            MP4 — 1080p
                        </strong>

                        <small>
                            Full HD quality
                        </small>

                    </span>

                    <span class="option-size">
                        ${displaySize(sizes["1080"])}
                    </span>

                    <span class="option-arrow">
                        ›
                    </span>

                </button>


                <button
                    type="button"
                    class="download-option option-gold"
                    data-format="mp4"
                    data-quality="best">

                    <span class="option-icon">
                        ★
                    </span>

                    <span class="option-text">

                        <strong>
                            MP4 — Best Quality
                        </strong>

                        <small>
                            Highest available quality
                        </small>

                    </span>

                    <span class="option-size">
                        ${displaySize(sizes["best"])}
                    </span>

                    <span class="option-arrow">
                        ›
                    </span>

                </button>


                <button
                    type="button"
                    class="download-option option-pink"
                    data-format="mp3"
                    data-quality="audio">

                    <span class="option-icon">
                        ♪
                    </span>

                    <span class="option-text">

                        <strong>
                            MP3 — Audio
                        </strong>

                        <small>
                            192 kbps MP3
                        </small>

                    </span>

                    <span class="option-size">
                        ${displaySize(
                            sizes["mp3"]
                        )}
                    </span>

                    <span class="option-arrow">
                        ›
                    </span>

                </button>

            </div>


            <button
                type="button"
                id="cancel-download"
                class="cancel-download">

                Cancel

            </button>

        </div>
    `;


    if (
        form &&
        form.parentNode
    ) {

        form.parentNode.insertBefore(
            box,
            form.nextSibling
        );
    }


    // =========================
    // OPTION BUTTONS
    // =========================

    box.querySelectorAll(
        "button[data-format]"
    ).forEach(button => {

        button.addEventListener(
            "click",
            () => {

                const format =
                    button.dataset.format;

                const quality =
                    button.dataset.quality;


                box.remove();


                startDownload(
                    url,
                    format,
                    quality,
                    videoTitle
                );
            }
        );
    });


    // =========================
    // CANCEL
    // =========================

    const cancelButton =
        box.querySelector(
            "#cancel-download"
        );


    if (cancelButton) {

        cancelButton.addEventListener(
            "click",
            () => {

                box.remove();

                if (msg) {

                    msg.textContent =
                        "Download cancelled.";
                }
            }
        );
    }


    if (msg) {

        msg.textContent =
            "Choose your download format.";
    }
}


// =========================
// START DOWNLOAD
// =========================

async function startDownload(
    url,
    format,
    quality,
    videoTitle
) {

    if (!url) {

        if (msg) {

            msg.textContent =
                "Please enter a valid video URL.";
        }

        return;
    }


    if (msg) {

        msg.textContent =
            "Preparing your download...";
    }


    const submitButton =
        form
            ? form.querySelector(
                'button[type="submit"]'
            )
            : null;


    let oldButtonText = "";


    if (submitButton) {

        oldButtonText =
            submitButton.innerText;

        submitButton.disabled =
            true;

        submitButton.innerText =
            "Downloading...";
    }


    try {

        const response =
            await fetch(
                API_DOWNLOAD,
                {
                    method: "POST",

                    headers: {
                        "Content-Type":
                            "application/json"
                    },

                    body: JSON.stringify({
                        url: url,
                        format: format,
                        quality: quality
                    })
                }
            );


        if (!response.ok) {

            let errorText =
                "Download failed.";

            try {

                const errorData =
                    await response.json();

                if (errorData.details) {

                    errorText =
                        errorData.details;

                } else if (errorData.error) {

                    errorText =
                        errorData.error;
                }

            } catch (e) {}


            throw new Error(
                errorText
            );
        }


        const blob =
            await response.blob();


        if (
            !blob ||
            blob.size === 0
        ) {

            throw new Error(
                "Empty file received."
            );
        }


        // =========================
        // FILE NAME
        // =========================

        let filename = "";


        const disposition =
            response.headers.get(
                "Content-Disposition"
            );


        // First try server filename
        if (disposition) {

            const utfMatch =
                disposition.match(
                    /filename\*=UTF-8''([^;]+)/i
                );


            if (utfMatch) {

                try {

                    filename =
                        decodeURIComponent(
                            utfMatch[1]
                        );

                } catch (e) {}
            }


            if (!filename) {

                const normalMatch =
                    disposition.match(
                        /filename="?([^"]+)"?/i
                    );


                if (normalMatch) {

                    filename =
                        normalMatch[1];
                }
            }
        }


        // =========================
        // IMPORTANT FALLBACK
        // =========================
        // Use the actual video title.
        // NEVER use LinkDrop as filename.

        if (!filename) {

            filename =
                cleanFilename(
                    videoTitle ||
                    "download"
                );


            if (
                format === "mp3" ||
                quality === "audio"
            ) {

                filename += ".mp3";

            } else {

                filename += ".mp4";
            }
        }


        filename =
            cleanFilename(
                filename
                    .replace(
                        /\.(mp4|mp3)$/i,
                        ""
                    )
            )
            +
            (
                format === "mp3" ||
                quality === "audio"
                    ? ".mp3"
                    : ".mp4"
            );


        // =========================
        // DOWNLOAD FILE
        // =========================

        const downloadURL =
            URL.createObjectURL(
                blob
            );


        const link =
            document.createElement("a");


        link.href =
            downloadURL;


        link.download =
            filename;


        document.body.appendChild(
            link
        );


        link.click();


        link.remove();


        setTimeout(
            () => {

                URL.revokeObjectURL(
                    downloadURL
                );

            },
            10000
        );


        // =========================
        // SAVE HISTORY
        // =========================

        history = [
            url,
            ...history.filter(
                item => item !== url
            )
        ].slice(0, 10);


        localStorage.setItem(
            "linkdrop-history",
            JSON.stringify(history)
        );


        render();


        if (msg) {

            msg.textContent =
                "Download completed successfully.";
        }


        input.value = "";


    } catch (error) {

        console.error(
            "LinkDrop download error:",
            error
        );


        if (msg) {

            msg.textContent =
                "Download failed: " +
                error.message;
        }


        alert(
            "Download failed:\n\n" +
            error.message
        );


    } finally {

        if (submitButton) {

            submitButton.disabled =
                false;

            submitButton.innerText =
                oldButtonText ||
                "Download";
        }
    }
}


// =========================
// HTML ESCAPE
// =========================

function escapeHtml(text) {

    return String(text)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}


// =========================
// FORM SUBMIT
// =========================

if (form) {

    form.addEventListener(
        "submit",
        async (event) => {

            event.preventDefault();


            const url =
                input.value.trim();


            if (!url) {

                if (msg) {

                    msg.textContent =
                        "Please paste a video URL.";
                }

                return;
            }


            try {

                const parsed =
                    new URL(url);


                if (
                    parsed.protocol !== "http:" &&
                    parsed.protocol !== "https:"
                ) {

                    throw new Error(
                        "Invalid URL"
                    );
                }


                await showOptions(
                    url
                );


            } catch (error) {

                if (msg) {

                    msg.textContent =
                        "Please enter a valid HTTP/HTTPS link.";
                }
            }
        }
    );
}


// =========================
// DARK MODE
// =========================

if (theme) {

    theme.addEventListener(
        "click",
        () => {

            document.body.classList.toggle(
                "dark"
            );
        }
    );
}


// =========================
// INITIAL LOAD
// =========================

render();
