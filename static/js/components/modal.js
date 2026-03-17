// Modal Component — replaces alert/confirm/prompt

let modalContainer = null;

function ensureContainer() {
  if (!modalContainer) {
    modalContainer = document.getElementById('modal-container');
  }
  return modalContainer;
}

/**
 * Show a confirmation modal.
 * @param {string} title
 * @param {string} message - HTML allowed
 * @param {Object} opts
 * @param {string} opts.confirmText - default "Confirm"
 * @param {string} opts.cancelText - default "Cancel"
 * @param {string} opts.confirmClass - default "btn"
 * @returns {Promise<boolean>}
 */
export function confirm(title, message, opts = {}) {
  return new Promise((resolve) => {
    const c = ensureContainer();
    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay';

    const confirmText = opts.confirmText || 'Confirm';
    const cancelText = opts.cancelText || 'Cancel';
    const confirmClass = opts.confirmClass || 'btn';

    overlay.innerHTML = `
      <div class="modal-box" role="dialog" aria-modal="true" aria-labelledby="modal-title">
        <h3 id="modal-title">${escapeHtml(title)}</h3>
        <div>${message}</div>
        <div class="modal-actions">
          <button class="btn-secondary btn modal-cancel">${escapeHtml(cancelText)}</button>
          <button class="${confirmClass} modal-confirm">${escapeHtml(confirmText)}</button>
        </div>
      </div>
    `;

    // Escape key closes
    const onKey = (e) => {
      if (e.key === 'Escape') close(false);
    };

    const close = (result) => {
      document.removeEventListener('keydown', onKey);
      overlay.remove();
      resolve(result);
    };

    overlay.querySelector('.modal-cancel').addEventListener('click', () => close(false));
    overlay.querySelector('.modal-confirm').addEventListener('click', () => close(true));
    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) close(false);
    });

    document.addEventListener('keydown', onKey);

    c.appendChild(overlay);
    overlay.querySelector('.modal-confirm').focus();
  });
}

/**
 * Show a custom modal with arbitrary HTML content.
 * Returns a close function.
 */
export function showModal(html) {
  const c = ensureContainer();
  const overlay = document.createElement('div');
  overlay.className = 'modal-overlay';
  overlay.innerHTML = `<div class="modal-box" role="dialog" aria-modal="true">${html}</div>`;

  const onKey = (e) => {
    if (e.key === 'Escape') close();
  };

  const close = () => {
    document.removeEventListener('keydown', onKey);
    overlay.remove();
  };

  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) close();
  });

  document.addEventListener('keydown', onKey);

  c.appendChild(overlay);
  return { close, el: overlay.querySelector('.modal-box') };
}

/**
 * Show a prompt modal.
 * @returns {Promise<string|null>} - null if cancelled
 */
export function prompt(title, message, defaultValue = '') {
  return new Promise((resolve) => {
    const c = ensureContainer();
    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay';
    overlay.innerHTML = `
      <div class="modal-box" role="dialog" aria-modal="true" aria-labelledby="prompt-title">
        <h3 id="prompt-title">${escapeHtml(title)}</h3>
        <p class="text-secondary text-sm mb-4">${escapeHtml(message)}</p>
        <input type="text" class="form-input modal-prompt-input" value="${escapeHtml(defaultValue)}">
        <div class="modal-actions">
          <button class="btn btn-secondary modal-cancel">Cancel</button>
          <button class="btn modal-confirm">OK</button>
        </div>
      </div>
    `;

    const input = overlay.querySelector('.modal-prompt-input');

    const onKey = (e) => {
      if (e.key === 'Escape') close(null);
    };

    const close = (val) => {
      document.removeEventListener('keydown', onKey);
      overlay.remove();
      resolve(val);
    };

    overlay.querySelector('.modal-cancel').addEventListener('click', () => close(null));
    overlay.querySelector('.modal-confirm').addEventListener('click', () => close(input.value));
    input.addEventListener('keydown', (e) => { if (e.key === 'Enter') close(input.value); });
    overlay.addEventListener('click', (e) => { if (e.target === overlay) close(null); });

    document.addEventListener('keydown', onKey);

    c.appendChild(overlay);
    input.focus();
    input.select();
  });
}

function escapeHtml(s) {
  const d = document.createElement('div');
  d.textContent = s || '';
  return d.innerHTML;
}
