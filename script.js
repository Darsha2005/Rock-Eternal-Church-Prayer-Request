(() => {
  const form = document.querySelector('#prayer-form');
  const nameInput = document.querySelector('#name');
  const prayerInput = document.querySelector('#prayer');
  const count = document.querySelector('#character-count');
  const error = document.querySelector('#form-error');
  const submit = form.querySelector('button[type="submit"]');
  const consent = document.querySelector('#share-consent');
  const showName = document.querySelector('#show-name');
  const category = document.querySelector('#category');

  const updateCount = () => {
    count.textContent = `${prayerInput.value.length} / 1200`;
  };

  prayerInput.addEventListener('input', () => {
    updateCount();
    if (prayerInput.value.trim()) {
      error.textContent = '';
      prayerInput.removeAttribute('aria-invalid');
    }
  });

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const message = prayerInput.value.trim();

    if (!message) {
      error.textContent = 'Please write a prayer request before continuing.';
      prayerInput.setAttribute('aria-invalid', 'true');
      prayerInput.focus();
      return;
    }

    if (!consent.checked) {
      error.textContent = 'Please confirm that your request can be shared with the Life Group.';
      consent.focus();
      return;
    }

    const request = {
      name: nameInput.value.trim(),
      message,
      category: category.value,
      showName: showName.checked,
      shareWithGroup: consent.checked,
    };

    submit.classList.add('is-sending');
    submit.disabled = true;
    submit.querySelector('span').textContent = 'Sending your prayer…';

    try {
      const response = await fetch('/api/prayers', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(request),
      });

      if (!response.ok) throw new Error('Could not save request');

      const savedRequest = await response.json();
      sessionStorage.setItem('rock-eternal-prayer-request', JSON.stringify(savedRequest));
      window.setTimeout(() => window.location.assign('heart.html'), 550);
    } catch {
      error.textContent = 'We could not save your request. Please make sure server.py is running in PyCharm, then try again.';
      submit.classList.remove('is-sending');
      submit.disabled = false;
      submit.querySelector('span').textContent = 'Place in the prayer heart';
    }
  });

  updateCount();
})();
