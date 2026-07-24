(() => {
  const loginPanel = document.querySelector('#admin-login');
  const dashboard = document.querySelector('#admin-dashboard');
  const loginForm = document.querySelector('#leader-login-form');
  const password = document.querySelector('#leader-password');
  const loginError = document.querySelector('#login-error');
  const requestList = document.querySelector('#admin-request-list');
  const summaryGrid = document.querySelector('#summary-grid');
  const dashboardMessage = document.querySelector('#dashboard-message');
  const filters = document.querySelector('#dashboard-filters');
  let activeStatus = 'all';

  const categoryOptions = [
    ['health', 'Health & healing'],
    ['family', 'Family & relationships'],
    ['urgent', 'Urgent need'],
    ['praise', 'Praise report'],
    ['other', 'Other'],
  ];

  const statusOptions = [
    ['pending', 'Needs review'],
    ['published', 'Publish to Prayer Wall'],
    ['answered', 'Mark as answered'],
    ['archived', 'Archive request'],
  ];

  const element = (tag, className, text) => {
    const item = document.createElement(tag);
    if (className) item.className = className;
    if (text !== undefined) item.textContent = text;
    return item;
  };

  const makeSelect = (options, value) => {
    const select = document.createElement('select');
    options.forEach(([optionValue, label]) => {
      const option = document.createElement('option');
      option.value = optionValue;
      option.textContent = label;
      option.selected = optionValue === value;
      select.append(option);
    });
    return select;
  };

  const renderRequest = (request) => {
    const card = element('article', 'admin-request-card');
    const cardTop = element('div', 'admin-card-top');
    const statusChip = element('span', `status-chip status-${request.status}`, request.status);
    const requestId = element('span', 'request-date', new Date(request.submittedAt).toLocaleDateString());
    cardTop.append(statusChip, requestId);

    const grid = element('div', 'admin-field-grid');
    const nameField = element('label', 'admin-field');
    nameField.append(element('span', '', 'Name'));
    const name = document.createElement('input');
    name.type = 'text';
    name.maxLength = 70;
    name.value = request.name;
    nameField.append(name);

    const categoryField = element('label', 'admin-field');
    categoryField.append(element('span', '', 'Category'));
    const category = makeSelect(categoryOptions, request.category);
    categoryField.append(category);

    const statusField = element('label', 'admin-field');
    statusField.append(element('span', '', 'Prayer Wall status'));
    const status = makeSelect(statusOptions, request.status);
    statusField.append(status);
    grid.append(nameField, categoryField, statusField);

    const messageField = element('label', 'admin-field message-field');
    messageField.append(element('span', '', 'Prayer request'));
    const message = document.createElement('textarea');
    message.maxLength = 1200;
    message.rows = 4;
    message.value = request.message;
    messageField.append(message);

    const controls = element('div', 'admin-card-controls');
    const showNameLabel = element('label', 'admin-show-name');
    const showName = document.createElement('input');
    showName.type = 'checkbox';
    showName.checked = request.showName;
    showNameLabel.append(showName, document.createTextNode('Show name to the Life Group'));
    const prayCount = element('span', 'admin-prayer-count', `${request.prayerCount} praying`);
    controls.append(showNameLabel, prayCount);

    const actions = element('div', 'admin-actions');
    const save = element('button', 'save-button', 'Save changes');
    save.type = 'button';
    const remove = element('button', 'delete-button', 'Delete');
    remove.type = 'button';
    save.addEventListener('click', async () => {
      save.disabled = true;
      dashboardMessage.textContent = '';
      try {
        const response = await fetch(`/api/admin/requests/${request.id}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            name: name.value,
            message: message.value,
            category: category.value,
            status: status.value,
            showName: showName.checked,
          }),
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || 'Could not save changes.');
        dashboardMessage.textContent = 'Changes saved.';
        await Promise.all([loadRequests(), loadSummary()]);
      } catch (error) {
        dashboardMessage.textContent = error.message || 'Could not save changes.';
        save.disabled = false;
      }
    });
    remove.addEventListener('click', async () => {
      const confirmed = window.confirm('Delete this prayer request permanently?');
      if (!confirmed) return;
      try {
        const response = await fetch(`/api/admin/requests/${request.id}`, { method: 'DELETE' });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || 'Could not delete this request.');
        dashboardMessage.textContent = 'Prayer request deleted.';
        await Promise.all([loadRequests(), loadSummary()]);
      } catch (error) {
        dashboardMessage.textContent = error.message || 'Could not delete this request.';
      }
    });
    actions.append(save, remove);
    card.append(cardTop, grid, messageField, controls, actions);
    return card;
  };

  const loadSummary = async () => {
    const response = await fetch('/api/admin/summary');
    if (!response.ok) throw new Error('Could not load summary.');
    const summary = await response.json();
    summaryGrid.replaceChildren();
    [
      ['pending', 'Needs review'],
      ['published', 'Live requests'],
      ['answered', 'Answered prayers'],
      ['archived', 'Archived'],
    ].forEach(([key, label]) => {
      const card = element('div', 'summary-card');
      card.append(element('strong', '', String(summary[key] || 0)), element('span', '', label));
      summaryGrid.append(card);
    });
  };

  const loadRequests = async () => {
    const response = await fetch(`/api/admin/requests?status=${activeStatus}`);
    if (!response.ok) throw new Error('Could not load prayer requests.');
    const requests = await response.json();
    requestList.replaceChildren();
    if (!requests.length) {
      requestList.append(element('p', 'loading-text', 'There are no requests in this section yet.'));
      return;
    }
    requests.forEach((request) => requestList.append(renderRequest(request)));
  };

  const showDashboard = async () => {
    loginPanel.hidden = true;
    dashboard.hidden = false;
    await Promise.all([loadSummary(), loadRequests()]);
  };

  loginForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    loginError.textContent = '';
    const button = loginForm.querySelector('button');
    button.disabled = true;
    try {
      const response = await fetch('/api/admin/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password: password.value }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || 'Could not sign in.');
      password.value = '';
      await showDashboard();
    } catch (error) {
      loginError.textContent = error.message || 'Could not sign in.';
      button.disabled = false;
    }
  });

  filters.addEventListener('click', async (event) => {
    const button = event.target.closest('button[data-status]');
    if (!button) return;
    activeStatus = button.dataset.status;
    filters.querySelectorAll('button').forEach((item) => item.classList.toggle('is-active', item === button));
    try {
      await loadRequests();
    } catch (error) {
      dashboardMessage.textContent = error.message || 'Could not load requests.';
    }
  });

  document.querySelector('#logout-button').addEventListener('click', async () => {
    await fetch('/api/admin/logout', { method: 'POST' });
    dashboard.hidden = true;
    loginPanel.hidden = false;
    password.focus();
  });

  fetch('/api/admin/session')
    .then((response) => (response.ok ? showDashboard() : undefined))
    .catch(() => undefined);
})();
