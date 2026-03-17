// Toast Notification Component — Meridian Design System

let container = null;

function ensureContainer() {
  if (!container) {
    container = document.getElementById('toast-container');
    if (!container) {
      container = document.createElement('div');
      container.id = 'toast-container';
      container.className = 'toast-container';
      document.body.appendChild(container);
    }
  }
  return container;
}

/**
 * Show a toast notification (Meridian style).
 *
 * New signature:
 *   showToast(title, type, duration, detail)
 *
 * Backward-compatible with the old signature:
 *   showToast(message, type, duration)
 * where message becomes the title and detail is omitted.
 *
 * @param {string} title    - Main message text
 * @param {'success'|'error'|'info'|'warning'} type - Semantic type
 * @param {number} duration - ms before auto-dismiss (0 = manual only)
 * @param {string} [detail] - Optional secondary detail text
 * @returns {Function} close - Call to dismiss the toast programmatically
 */
export function showToast(title, type = 'info', duration = 4000, detail) {
  const c = ensureContainer();
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.setAttribute('role', type === 'error' || type === 'warning' ? 'alert' : 'status');
  toast.setAttribute('aria-live', type === 'error' || type === 'warning' ? 'assertive' : 'polite');

  // Build inner HTML: dot + content block + close button
  let contentHtml = `<p class="toast-title">${escapeHtml(title)}</p>`;
  if (detail) {
    contentHtml += `<p class="toast-detail">${escapeHtml(detail)}</p>`;
  }

  toast.innerHTML = `
    <div class="toast-dot"></div>
    <div class="toast-content">
      ${contentHtml}
    </div>
    <button class="toast-close" aria-label="Close">\u00D7</button>
  `;

  let dismissed = false;

  const close = () => {
    if (dismissed) return;
    dismissed = true;
    // Apply exit class for CSS transition (opacity + translateX)
    toast.classList.add('toast-exit');
    // Remove from DOM after the transition completes
    const onEnd = () => toast.remove();
    toast.addEventListener('transitionend', onEnd, { once: true });
    // Fallback removal in case transitionend doesn't fire
    setTimeout(onEnd, 300);
  };

  toast.querySelector('.toast-close').addEventListener('click', close);

  c.appendChild(toast);

  if (duration > 0) {
    setTimeout(close, duration);
  }

  return close;
}

function escapeHtml(s) {
  const d = document.createElement('div');
  d.textContent = s || '';
  return d.innerHTML;
}
