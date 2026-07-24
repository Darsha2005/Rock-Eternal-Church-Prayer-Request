(() => {
  const stored = sessionStorage.getItem('rock-eternal-prayer-request');
  const note = document.querySelector('#prayer-note');
  const noteName = document.querySelector('#note-name');
  const noteMessage = document.querySelector('#note-message');
  const subtitle = document.querySelector('#heart-subtitle');
  const noteLabel = document.querySelector('#note-label');
  const noteFooter = document.querySelector('#note-footer-status');

  let request;
  try {
    request = stored ? JSON.parse(stored) : null;
  } catch {
    request = null;
  }

  if (request?.message) {
    noteName.textContent = request.name ? `For ${request.name},` : 'Dear friend,';
    noteMessage.textContent = request.message;
    subtitle.textContent = request.name
      ? `${request.name}, your request is safely with a Life Group leader for review.`
      : 'Your request is safely with a Life Group leader for review.';
    if (request.status === 'pending') {
      noteLabel.textContent = 'SENT FOR LEADER REVIEW';
      noteFooter.textContent = 'Held in prayer';
    }
  } else {
    noteName.textContent = 'A place is waiting';
    noteMessage.textContent = 'Share your prayer request and it will be placed in this heart.';
    subtitle.textContent = 'A prayer request has not been added yet.';
  }

  requestAnimationFrame(() => {
    window.setTimeout(() => note.classList.add('is-landed'), 350);
  });

  const prayerList = document.querySelector('#recent-prayer-list');

  const previewCard = (prayer) => {
    const card = document.createElement('article');
    card.className = 'preview-card';
    const name = document.createElement('h3');
    const message = document.createElement('p');
    name.textContent = prayer.name ? prayer.name : 'Anonymous';
    message.textContent = prayer.message;
    card.append(name, message);
    return card;
  };

  const loadPreview = async () => {
    try {
      const response = await fetch('/api/prayers');
      if (!response.ok) throw new Error('Could not load requests');
      const prayers = await response.json();
      const otherPrayers = prayers.filter((prayer) => prayer.id !== request?.id).slice(0, 3);
      prayerList.replaceChildren();

      if (!otherPrayers.length) {
        const empty = document.createElement('p');
        empty.className = 'loading-text';
        empty.textContent = 'Your request is the first one here. Thank you for sharing it in faith.';
        prayerList.append(empty);
        return;
      }

      otherPrayers.forEach((prayer) => prayerList.append(previewCard(prayer)));
    } catch {
      prayerList.replaceChildren();
      const message = document.createElement('p');
      message.className = 'loading-text';
      message.textContent = 'Start server.py in PyCharm to see the shared Prayer Wall.';
      prayerList.append(message);
    }
  };

  loadPreview();
})();
