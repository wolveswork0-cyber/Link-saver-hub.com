const API_URL = "https://linkdrop-pro-3clf.onrender.com/api/download";

const form = document.getElementById("form");
const input = document.getElementById("url");
const msg = document.getElementById("msg");
const list = document.getElementById("list");
const clearBtn = document.getElementById("clear");

form.addEventListener("submit", async (e) => {
  e.preventDefault();

  const url = input.value.trim();

  if (!url || !/^https?:\/\//i.test(url)) {
    msg.textContent = "Please enter a valid URL.";
    return;
  }

  msg.textContent = "⏳ Processing... Please wait.";
  
  try {
    const response = await fetch(API_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ url })
    });

    if (!response.ok) {
      let errorMessage = "Download failed.";

      try {
        const data = await response.json();
        errorMessage = data.error || errorMessage;
      } catch {}

      throw new Error(errorMessage);
    }

    const blob = await response.blob();

    let filename = "LinkDrop-download";

    const disposition = response.headers.get("Content-Disposition");

    if (disposition) {
      const match = disposition.match(/filename="?([^"]+)"?/i);
      if (match) {
        filename = match[1];
      }
    }

    const downloadUrl = URL.createObjectURL(blob);

    const a = document.createElement("a");
    a.href = downloadUrl;
    a.download = filename;

    document.body.appendChild(a);
    a.click();
    a.remove();

    URL.revokeObjectURL(downloadUrl);

    msg.textContent = "✅ Download started.";

    saveHistory(url);
    input.value = "";

  } catch (error) {
    console.error(error);
    msg.textContent = "❌ " + error.message;
  }
});


function saveHistory(url) {
  let history = JSON.parse(localStorage.getItem("linkdrop_history") || "[]");

  history.unshift(url);
  history = [...new Set(history)].slice(0, 10);

  localStorage.setItem("linkdrop_history", JSON.stringify(history));

  showHistory();
}


function showHistory() {
  const history = JSON.parse(localStorage.getItem("linkdrop_history") || "[]");

  if (!history.length) {
    list.innerHTML = '<p class="empty">No downloads yet.</p>';
    return;
  }

  list.innerHTML = history.map(url => `
    <div class="historyItem">
      <span>${escapeHtml(url)}</span>
    </div>
  `).join("");
}


clearBtn.addEventListener("click", () => {
  localStorage.removeItem("linkdrop_history");
  showHistory();
});


function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}


showHistory();
