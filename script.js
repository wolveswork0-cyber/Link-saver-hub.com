const API_URL = "https://linkdrop-pro-3clf.onrender.com/api/download";

const form = document.getElementById("downloadForm");
const input = document.getElementById("urlInput");
const status = document.getElementById("status");

form.addEventListener("submit", async (e) => {
  e.preventDefault();

  const url = input.value.trim();

  if (!url || !/^https?:\/\//i.test(url)) {
    status.textContent = "Please enter a valid URL.";
    return;
  }

  status.textContent = "Preparing download... Please wait.";

  try {
    const response = await fetch(API_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ url })
    });

    if (!response.ok) {
      let message = "Download failed.";
      try {
        const data = await response.json();
        message = data.error || message;
      } catch {}
      throw new Error(message);
    }

    const blob = await response.blob();

    const disposition = response.headers.get("Content-Disposition");
    let filename = "download";

    if (disposition) {
      const match = disposition.match(/filename="?([^"]+)"?/i);
      if (match) filename = match[1];
    }

    const downloadUrl = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = downloadUrl;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();

    URL.revokeObjectURL(downloadUrl);

    status.textContent = "Download started successfully.";
  } catch (error) {
    console.error(error);
    status.textContent = error.message || "Download failed.";
  }
});
