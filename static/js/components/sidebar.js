// Sidebar Navigation Component
import { getApiKey, setApiKey, hasApiKey } from '../api.js';
import { navigate } from '../router.js';
import { esc } from '../state.js';
import {
  iconDashboard,
  iconExtractions,
  iconEntities,
  iconTaxonomy,
  iconAnalytics,
  iconComparison,
  iconSystem,
} from './icons.js';

const NAV_ITEMS = [
  { route: '/', icon: iconDashboard, label: 'Dashboard' },
  { route: '/extractions', icon: iconExtractions, label: 'Extractions' },
  { route: '/entities', icon: iconEntities, label: 'Entities' },
  { route: '/taxonomy', icon: iconTaxonomy, label: 'Taxonomy' },
  { route: '/analytics', icon: iconAnalytics, label: 'Analytics' },
  { route: '/comparison', icon: iconComparison, label: 'Comparison' },
];

const ADMIN_ITEMS = [
  { route: '/admin', icon: iconSystem, label: 'System' },
];

export function renderSidebar(container) {
  container.innerHTML = `
    <div class="sidebar-brand">
      <div class="brand-row">
        <div class="logomark"><div class="logomark-inner"></div></div>
        <h1>DebtFund</h1>
      </div>
    </div>
    <nav class="sidebar-nav" aria-label="Main navigation">
      <p class="sidebar-section" aria-hidden="true">Workspace</p>
      ${NAV_ITEMS.map(item => navItem(item)).join('')}
      <p class="sidebar-section" aria-hidden="true">Admin</p>
      ${ADMIN_ITEMS.map(item => navItem(item)).join('')}
    </nav>
    <div class="sidebar-footer">
      <div class="sidebar-key" role="group" aria-label="API key configuration">
        <input type="password" id="sidebar-api-key" placeholder="API Key" value="${esc(getApiKey())}" aria-label="API key">
        <button id="sidebar-save-key" aria-label="Save API key">Save</button>
      </div>
      <div class="sidebar-health" role="status" aria-live="polite">
        <span class="health-dot" id="health-dot" aria-hidden="true"></span>
        <span id="health-text">Checking...</span>
      </div>
    </div>
  `;

  // Nav click handlers
  container.querySelectorAll('.sidebar-item').forEach(item => {
    item.addEventListener('click', (e) => {
      e.preventDefault();
      navigate(item.dataset.route);
    });
  });

  // API key save
  const keyInput = container.querySelector('#sidebar-api-key');
  container.querySelector('#sidebar-save-key').addEventListener('click', () => {
    setApiKey(keyInput.value);
    import('../components/toast.js').then(m => m.showToast('API key saved', 'success'));
  });

  // Also save on Enter
  keyInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      setApiKey(keyInput.value);
      import('../components/toast.js').then(m => m.showToast('API key saved', 'success'));
    }
  });

  // Check health
  checkHealth();

  // First-time user prompt: highlight API key input if not configured
  if (!hasApiKey()) {
    keyInput.classList.add('pulse-highlight');
    keyInput.placeholder = 'Enter your API key to get started';
    const hint = document.createElement('p');
    hint.className = 'text-sm';
    hint.style.cssText = 'color:#C47D00;margin:4px 0 0;font-size:10.5px';
    hint.textContent = 'An API key is required to use DebtFund.';
    container.querySelector('.sidebar-key').appendChild(hint);
  }
}

function navItem({ route, icon, label }) {
  return `<a class="sidebar-item" data-route="${route}" href="#${route}" aria-label="${label}">
    <div class="icon" aria-hidden="true">${icon()}</div>
    <span class="label">${label}</span>
  </a>`;
}

async function checkHealth() {
  const dot = document.getElementById('health-dot');
  const text = document.getElementById('health-text');
  if (!dot) return;

  try {
    const res = await fetch('/health/readiness');
    const data = await res.json();
    if (res.ok && data.status === 'ready') {
      dot.className = 'health-dot ok';
      dot.style.background = '#4CAF7D';
      text.textContent = 'API healthy';
    } else {
      dot.className = 'health-dot warn';
      dot.style.background = '#C47D00';
      text.textContent = 'Degraded';
    }
  } catch {
    dot.className = 'health-dot error';
    dot.style.background = '#A32626';
    text.textContent = 'Offline';
  }

  // Re-check every 60s
  setTimeout(checkHealth, 60000);
}
