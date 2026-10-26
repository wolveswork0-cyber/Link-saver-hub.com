const form = document.querySelector("#form");
const input = document.querySelector("#url");
const msg = document.querySelector("#msg");
const list = document.querySelector("#list");
const theme = document.querySelector("#theme");

const API_URL = "https://linkdrop-pro-3clf.onrender.com/api/download";

let history = JSON.parse(
    localStorage.getItem("linkdrop-history") || "[]"
);


// ===============================
// HISTORY
// ===============================

function render() {
    if (!list) return;

    list.innerHTML = history.length
        ? history.map((u, i) => `
            <div class="item">
                <a href="${u}" target="_blank" rel="noopener">
                    ${u}
                </a>
                <button onclick="removeItem(${i})">×</button>
            </div>
        `).join("")
        : '<p class="empty">No downloads yet.</p>';
}


function removeItem(i) {
    history.splice(i, 1);

    localStorage.setItem(
        "linkdrop-history",
        JSON.stringify(history)
    );

    render();
}


const clearButton = document.querySelector("#clear");

if (clearButton) {
    clearButton.onclick = () => {
        history = [];

        localStorage.removeItem("linkdrop-history");

        render();
    };
}


// ===============================
// CREATE DOWNLOAD OPTIONS
// ===============================

function showOptions() {

    // Remove old options if already present
    const oldBox = document.querySelector("#download-options");

    if (oldBox) {
        oldBox.remove();
    }

    const box = document.createElement("div");

    box.id = "download-options";

    box.innerHTML = `
        <div class="download-options-inner">

            <h3>Select Download Format</h3>

            <button type="button" data-format="mp4" data-quality="480">
                MP4 — 480p
            </button>

            <button type="button" data-format="mp4" data-quality="720">
                MP4 — 720p
            </button>

            <button type="button" data-format="mp4" data-quality="1080">
                MP4 — 1080p
            </button>

            <button type="button" data-format="mp4" data-quality="best">
                MP4 — Best Quality
            </button>

            <button type="button" data-format="mp3" data-quality="audio">
                MP3 — Audio
            </button>

            <button type="button" id="cancel-download">
                Cancel
            </button>

        </div>
    `;

    form.parentNode.insertBefore(box, form.nextSibling);


    // ===============================
    // OPTION BUTTONS
    // ===============================

    box.querySelectorAll(
        "button[data-format]"
    ).forEach(button => {

        button.addEventListener("click", () => {

            const format = button.dataset.format;
            const quality = button.dataset.quality;

            box.remove();

            startDownload(
                input.value.trim(),
                format,
                quality
            );
        });
    });


    // ===============================
    // CANCEL
    // ===============================

    const cancel = box.querySelector(
        "#cancel-download"
    );

    if (cancel) {
        cancel.addEventListener("click", () => {
            box.remove();

            if (msg) {
                msg.textContent =
                    "Download cancelled.";
            }
        });
    }
}


// ===============================
// START DOWNLOAD
// ===============================

async function startDownload(
    url,
    format,
    quality
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
        form.querySelector(
            'button[type="submit"]'
        );

    let oldButtonText = "";

    if (submitButton) {
        oldButtonText =
            submitButton.innerText;

        submitButton.disabled = true;

        submitButton.innerText =
            "Downloading...";
    }


    try {

        const response = await fetch(
            API_URL,
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
                }
                else if (errorData.error) {
                    errorText =
                        errorData.error;
                }

            } catch (e) {
                // Ignore JSON error
            }

            throw new Error(errorText);
        }


        const blob =
            await response.blob();


        if (!blob ||
            blob.size === 0) {

            throw new Error(
                "Empty file received."
            );
        }


        // ===============================
        // FILE NAME
        // ===============================

        let filename = "";

        const disposition =
            response.headers.get(
                "Content-Disposition"
            );


        if (disposition) {

            const utfMatch =
                disposition.match(
                    /filename\*=UTF-8''([^;]+)/i
                );

            if (utfMatch) {

                filename =
                    decodeURIComponent(
                        utfMatch[1]
                    );
            }
            else {

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


        // Fallback filename

        if (!filename) {

            if (format === "mp3") {

                filename =
                    "LinkDrop-Audio.mp3";

            }
            else if (quality === "480") {

                filename =
                    "LinkDrop-480p.mp4";

            }
            else if (quality === "720") {

                filename =
                    "LinkDrop-720p.mp4";

            }
            else if (quality === "1080") {

                filename =
                    "LinkDrop-1080p.mp4";

            }
            else {

                filename =
                    "LinkDrop-Best-Quality.mp4";
            }
        }


        // ===============================
        // BROWSER DOWNLOAD
        // ===============================

        const downloadURL =
            URL.createObjectURL(blob);

        const link =
            document.createElement("a");

        link.href = downloadURL;

        link.download = filename;

        document.body.appendChild(link);

        link.click();

        link.remove();


        setTimeout(() => {

            URL.revokeObjectURL(
                downloadURL
            );

        }, 10000);


        // ===============================
        // HISTORY
        // ===============================

        history = [
            url,
            ...history.filter(
                x => x !== url
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

            submitButton.disabled = false;

            submitButton.innerText =
                oldButtonText ||
                "Download";
        }
    }
}


// ===============================
// FORM SUBMIT
// ===============================

if (form) {

    form.onsubmit = (e) => {

        e.preventDefault();

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
                parsed.protocol !==
                    "http:" &&
                parsed.protocol !==
                    "https:"
            ) {

                throw new Error(
                    "Invalid URL"
                );
            }


            // Show format/quality options
            showOptions();

        } catch (error) {

            if (msg) {

                msg.textContent =
                    "Please enter a valid HTTP/HTTPS link.";
            }
        }
    };
}


// ===============================
// DARK MODE
// ===============================

if (theme) {

    theme.onclick = () => {

        document.body.classList.toggle(
            "dark"
        );
    };
}


// ===============================
// INITIALIZE
// ===============================

render();
