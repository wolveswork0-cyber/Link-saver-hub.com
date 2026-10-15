const form = document.querySelector('#form');
const input = document.querySelector('#url');
const msg = document.querySelector('#msg');
const list = document.querySelector('#list');

let history = JSON.parse(
  localStorage.getItem('linkdrop-history') || '[]'
);

function render() {
  list.innerHTML = history.length
    ? history.map((u, i) =>
        `<div class="item">
          <a href="${u}" target="_blank" rel="noopener">${u}</a>
          <button onclick="removeItem(${i})">×</button>
        </div>`
      ).join('')
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

form.onsubmit = e => {
  e.preventDefault();

  try {
    const u = new URL(input.value.trim());

    if (!/^https?:$/.test(u.protocol)) throw 0;

    const a = document.createElement('a');
    a.href = u.href;
    a.target = '_blank';
    a.rel = 'noopener noreferrer';
    a.download = '';

    document.body.appendChild(a);
    a.click();
    a.remove();

    history = [
      u.href,
      ...history.filter(x => x !== u.href)
    ].slice(0, 10);

    localStorage.setItem(
      'linkdrop-history',
      JSON.stringify(history)
    );

    render();

    msg.textContent =
      'Download request sent. If a webpage opens, the host does not allow direct browser downloading.';

    input.value = '';

  } catch {
    msg.textContent =
      'Please enter a valid HTTP/HTTPS link.';
  }
};

document.querySelector('#theme').onclick = () => {
  document.body.classList.toggle('dark');
};

render();
