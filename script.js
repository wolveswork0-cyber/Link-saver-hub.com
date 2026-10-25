const form = document.querySelector('#form');
const input = document.querySelector('#url');
const msg = document.querySelector('#msg');
const list = document.querySelector('#list');

const API_URL = 'https://linkdrop-pro-3clf.onrender.com';

let history = JSON.parse(
  localStorage.getItem('linkdrop-history') || '[]'
);

function render() {
  list.innerHTML = history.length
    ? history.map((u, i) => `
        <div class="item">
          <a href="${u}" target="_blank" rel="noopener">${u}</a>
          <button onclick="removeItem(${i})">×</button>
        </div>
      `).join('')
    : '<p class="empty">No downloads yet.</p>';
}

function removeItem(i) {
  history.splice(i, 1);
  localStorage.setItem(
    'linkdrop-history',
    JSON.stringify(history)
  );
  render();
}

document.querySelector('#clear').onclick = () => {
  history = [];
  localStorage.removeItem('linkdrop-history');
  render();
};

form.onsubmit = async (e) => {
  e.preventDefault();

  const url = input.value.trim();

  try {
    const u = new URL(url);

    if (!/^https?:$/.test(u.protocol)) {
      throw new Error();
    }

    const choice = prompt(
      'Download option select karein:\n\n' +
      '1 = MP4 480p\n' +
      '2 = MP4 720p\n' +
      '3 = MP4 1080p\n' +
      '4 = Best Quality\n' +
      '5 = MP3 Audio'
    );

    const options = {
      '1': { format: 'mp4', quality: '480' },
      '2': { format: 'mp4', quality: '720' },
      '3': { format: 'mp4', quality: '1080' },
      '4': { format: 'mp4', quality: 'best' },
      '5': { format: 'mp3', quality: 'audio' }
    };

    if (!options[choice]) {
      msg.textContent = 'Download cancelled.';
      return;
    }

    msg.textContent = 'Preparing download... Please wait.';

    const response = await fetch(
      API_URL + '/api/download',
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          url: u.href,
          format: options[choice].format,
          quality: options[choice].quality
        })
      }
    );

    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(
        error.details ||
        error.error ||
        'Download failed.'
      );
    }

    const blob = await response.blob();

    const blobUrl = URL.createObjectURL(blob);
    const a = document.createElement('a');

    a.href = blobUrl;
    a.download =
      options[choice].format === 'mp3'
        ? 'LinkDrop-Audio.mp3'
        : 'LinkDrop-Video.mp4';

    document.body.appendChild(a);
    a.click();
    a.remove();

    URL.revokeObjectURL(blobUrl);

    history = [
      u.href,
      ...history.filter(x => x !== u.href)
    ].slice(0, 10);

    localStorage.setItem(
      'linkdrop-history',
      JSON.stringify(history)
    );

    render();

    msg.textContent = 'Download completed.';
    input.value = '';

  } catch (error) {
    console.error(error);

    msg.textContent =
      error.message ||
      'Please enter a valid HTTP/HTTPS link.';
  }
};

document.querySelector('#theme').onclick = () => {
  document.body.classList.toggle('dark');
};

render();
