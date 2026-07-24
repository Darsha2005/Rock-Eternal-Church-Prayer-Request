(() => {
  const list = document.querySelector('#prayer-wall-list');
  const error = document.querySelector('#wall-error');
  let activeFilter = 'published';

  const requestCard = (prayer) => {
    const card = document.createElement('article');
    card.className = 'wall-card';

    const top = document.createElement('div');
    top.className = 'wall-card-top';
    const name = document.createElement('h2');
    name.textContent = prayer.name ? prayer.name : 'Anonymous';
    const tag = document.createElement('span');
    tag.textContent = prayer.status === 'answered' ? 'ANSWERED PRAYER' : prayer.category.toUpperCase();
    top.append(name, tag);

    const message = document.createElement('p');
    message.className = 'wall-message';
    message.textContent = prayer.message;

    const footer = document.createElement('div');
    footer.className = 'wall-card-footer';
    const count = document.createElement('span');
    const prayers = Number(prayer.prayerCount) || 0;
    count.textContent = prayers ? `${prayers} praying` : 'Be the first to pray';
    const button = document.createElement('button');
    button.className = 'pray-button';
    button.type = 'button';
    button.textContent = 'I prayed for this';
    button.addEventListener('click', async () => {
      button.disabled = true;
      try {
        const response = await fetch(`/api/prayers/${prayer.id}/pray`, { method: 'POST' });
        if (!response.ok) throw new Error('Could not record prayer');
        const updated = await response.json();
        const updatedCount = Number(updated.prayerCount) || 0;
        count.textContent = `${updatedCount} praying`;
        button.textContent = 'Prayer recorded ✦';
      } catch {
        button.disabled = false;
        error.textContent = 'Your prayer could not be recorded. Please try again.';
      }
    });
    footer.append(count, button);
    card.append(top, message, footer);
    return card;
  };

  const loadRequests = async (status = activeFilter) => {
    activeFilter = status;
    try {
      const response = await fetch(`/api/prayers?status=${status}`);
      if (!response.ok) throw new Error('Could not load requests');
      const prayers = await response.json();
      list.replaceChildren();

      if (!prayers.length) {
        const empty = document.createElement('p');
        empty.className = 'loading-text';
        empty.textContent = status === 'answered'
          ? 'No answered prayers have been shared yet. We look forward to celebrating with you.'
          : 'No requests have been shared yet. You can be the first to add one.';
        list.append(empty);
        return;
      }

      prayers.forEach((prayer) => list.append(requestCard(prayer)));
    } catch {
      list.replaceChildren();
      error.textContent = 'The Prayer Wall needs server.py to be running in PyCharm.';
    }
  };

  const filterBar = document.createElement('div');
  filterBar.className = 'wall-filters';
  const published = document.createElement('button');
  published.type = 'button';
  published.textContent = 'Current prayer needs';
  published.className = 'filter-button is-active';
  const answered = document.createElement('button');
  answered.type = 'button';
  answered.textContent = 'Answered prayers';
  answered.className = 'filter-button';
  const setFilter = (status) => {
    published.classList.toggle('is-active', status === 'published');
    answered.classList.toggle('is-active', status === 'answered');
    loadRequests(status);
  };
  published.addEventListener('click', () => setFilter('published'));
  answered.addEventListener('click', () => setFilter('answered'));
  filterBar.append(published, answered);
  list.before(filterBar);

  loadRequests('published');
})();
