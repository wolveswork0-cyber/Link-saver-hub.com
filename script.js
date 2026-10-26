const form = document.getElementById("form");
const urlInput = document.getElementById("url");

const API_URL = "https://linkdrop-pro-3clf.onrender.com/api/download";

form.addEventListener("submit", async (e) => {
    e.preventDefault();

    const url = urlInput.value.trim();

    if (!url) {
        alert("Please paste a video URL.");
        return;
    }

    // Show format options
    const choice = prompt(
        "Select Download Format:\n\n" +
        "1 = MP4 480p\n" +
        "2 = MP4 720p\n" +
        "3 = MP4 1080p\n" +
        "4 = Best Quality\n" +
        "5 = MP3 Audio\n\n" +
        "Enter 1, 2, 3, 4 or 5:"
    );

    if (!choice) {
        return;
    }

    let format = "mp4";
    let quality = "best";

    switch (choice.trim()) {
        case "1":
            format = "mp4";
            quality = "480";
            break;

        case "2":
            format = "mp4";
            quality = "720";
            break;

        case "3":
            format = "mp4";
            quality = "1080";
            break;

        case "4":
            format = "mp4";
            quality = "best";
            break;

        case "5":
            format = "mp3";
            quality = "audio";
            break;

        default:
            alert("Invalid option. Please select 1, 2, 3, 4 or 5.");
            return;
    }

    try {
        const button = form.querySelector("button[type='submit']");
        const oldText = button ? button.innerText : "";

        if (button) {
            button.disabled = true;
            button.innerText = "Downloading...";
        }

        const response = await fetch(API_URL, {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                url: url,
                format: format,
                quality: quality
            })
        });

        if (!response.ok) {
            let errorMessage = "Download failed.";

            try {
                const errorData = await response.json();

                if (errorData.details) {
                    errorMessage = errorData.details;
                } else if (errorData.error) {
                    errorMessage = errorData.error;
                }
            } catch (_) {}

            throw new Error(errorMessage);
        }

        const blob = await response.blob();

        if (!blob || blob.size === 0) {
            throw new Error("Empty file received.");
        }

        const contentDisposition =
            response.headers.get("Content-Disposition") || "";

        let filename = "";

        const filenameMatch =
            contentDisposition.match(/filename\*=UTF-8''([^;]+)/i);

        if (filenameMatch) {
            filename = decodeURIComponent(filenameMatch[1]);
        } else {
            const normalMatch =
                contentDisposition.match(/filename="?([^"]+)"?/i);

            if (normalMatch) {
                filename = normalMatch[1];
            }
        }

        if (!filename) {
            if (format === "mp3") {
                filename = "LinkDrop-Audio.mp3";
            } else {
                filename = `LinkDrop-${quality}.mp4`;
            }
        }

        const downloadUrl = URL.createObjectURL(blob);

        const a = document.createElement("a");
        a.href = downloadUrl;
        a.download = filename;

        document.body.appendChild(a);
        a.click();
        a.remove();

        setTimeout(() => {
            URL.revokeObjectURL(downloadUrl);
        }, 10000);

    } catch (error) {
        console.error("Download error:", error);
        alert("Download failed: " + error.message);

    } finally {
        const button = form.querySelector("button[type='submit']");

        if (button) {
            button.disabled = false;
            button.innerText = "Download";
        }
    }
});
