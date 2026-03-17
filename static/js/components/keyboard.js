// Keyboard Shortcuts Module — DebtFund SPA
//
// Supports single-key shortcuts ('u', '?') and two-key chord
// shortcuts ('g d', 'g e', etc.).  The chord prefix times out
// after 800 ms so normal typing is not disrupted.

import { navigate } from '../router.js';
import { showModal } from '../components/modal.js';

let _enabled = true;
let _pendingPrefix = null;
let _prefixTimer = null;
let _keydownHandler = null;

export function initKeyboard() {
  _keydownHandler = handleKeydown;
  document.addEventListener('keydown', _keydownHandler);
}

export function destroyKeyboard() {
  if (_keydownHandler) {
    document.removeEventListener('keydown', _keydownHandler);
    _keydownHandler = null;
  }
  if (_prefixTimer) clearTimeout(_prefixTimer);
}

function handleKeydown(e) {
  // Don't fire if user is typing in an input, textarea, select, or contenteditable
  const tag = e.target.tagName;
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || e.target.isContentEditable) return;
  // Don't fire if modifier keys are held (allow Ctrl+C etc.)
  if (e.ctrlKey || e.metaKey || e.altKey) return;

  const key = e.key.toLowerCase();

  // Handle chord: if we have a pending prefix
  if (_pendingPrefix === 'g') {
    clearTimeout(_prefixTimer);
    _pendingPrefix = null;

    const routes = {
      d: '/',
      e: '/extractions',
      n: '/entities',
      t: '/taxonomy',
      a: '/analytics',
      s: '/admin',
    };

    if (routes[key]) {
      e.preventDefault();
      navigate(routes[key]);
      return;
    }
    // If key doesn't match, fall through to single-key handling
  }

  // Start chord prefix
  if (key === 'g') {
    _pendingPrefix = 'g';
    _prefixTimer = setTimeout(() => { _pendingPrefix = null; }, 800);
    return;
  }

  // Single key shortcuts
  if (key === 'u') {
    e.preventDefault();
    // Try to find upload zone on dashboard, or show toast
    const uploadInput = document.querySelector('#dash-upload input[type="file"]');
    if (uploadInput) {
      uploadInput.click();
    } else {
      // Import showToast dynamically to avoid circular dependency
      import('../components/toast.js').then(m => {
        m.showToast('Navigate to Dashboard to upload', 'info');
      });
    }
    return;
  }

  if (key === '?') {
    e.preventDefault();
    showHelpOverlay();
    return;
  }
}

function showHelpOverlay() {
  const shortcuts = [
    { keys: 'g d', desc: 'Go to Dashboard' },
    { keys: 'g e', desc: 'Go to Extractions' },
    { keys: 'g n', desc: 'Go to Entities' },
    { keys: 'g t', desc: 'Go to Taxonomy' },
    { keys: 'g a', desc: 'Go to Analytics' },
    { keys: 'g s', desc: 'Go to System' },
    { keys: 'u', desc: 'Upload file' },
    { keys: '?', desc: 'Show this help' },
  ];

  let html = '<div style="max-width:360px">';
  html += '<h3 style="font-family:var(--font-serif);font-size:1.25rem;font-weight:400;margin:0 0 16px">Keyboard Shortcuts</h3>';
  html += '<table style="width:100%;font-size:12px;border-collapse:collapse">';

  for (const s of shortcuts) {
    const keyHtml = s.keys.split(' ').map(k =>
      `<kbd style="
        display:inline-block;padding:2px 6px;
        background:var(--color-background-secondary);
        border:0.5px solid var(--color-border-secondary);
        border-radius:4px;font-family:var(--font-mono);
        font-size:11px;min-width:20px;text-align:center
      ">${k}</kbd>`
    ).join(' <span style="color:var(--color-text-tertiary);font-size:10px">then</span> ');

    html += `<tr style="border-bottom:0.5px solid var(--color-border-tertiary)">
      <td style="padding:8px 12px 8px 0;white-space:nowrap">${keyHtml}</td>
      <td style="padding:8px 0;color:var(--color-text-secondary)">${s.desc}</td>
    </tr>`;
  }

  html += '</table></div>';

  showModal(html);
}
