// TabIntelligence Hash-Based Router

const routes = [];
let currentDestroy = null;
let currentModule = null;
let contentEl = null;

/**
 * Register a route.
 * @param {string} pattern - Hash pattern like '/extractions/:jobId'
 * @param {Function} handler - async function(container, params) that renders the page
 * @param {Function} [destroy] - optional cleanup function
 * @param {Object} [pageModule] - optional page module with canLeave() export
 */
export function addRoute(pattern, handler, destroy, pageModule) {
  const paramNames = [];
  const regexStr = pattern.replace(/:([^/]+)/g, (_, name) => {
    paramNames.push(name);
    return '([^/]+)';
  });
  const regex = new RegExp('^' + regexStr + '$');
  routes.push({ pattern, regex, paramNames, handler, destroy, pageModule });
}

/** Navigate to a hash route */
export function navigate(hash) {
  window.location.hash = '#' + hash;
}

/** Get current route path (without #) */
export function currentPath() {
  return window.location.hash.slice(1) || '/';
}

/** Initialize router — call once on app startup */
export function initRouter(container) {
  contentEl = container;
  window.addEventListener('hashchange', () => handleRoute());
  handleRoute();
}

async function handleRoute() {
  const path = currentPath();

  // canLeave guard: check if the current page allows navigation away
  if (currentModule && currentModule.canLeave) {
    try {
      const ok = await currentModule.canLeave();
      if (!ok) return; // abort navigation
    } catch (e) {
      // If canLeave throws, allow navigation
    }
  }

  // Cleanup previous page
  if (currentDestroy) {
    try { currentDestroy(); } catch (e) { /* ignore */ }
    currentDestroy = null;
  }
  currentModule = null;

  // Find matching route
  for (const route of routes) {
    const match = path.match(route.regex);
    if (match) {
      const params = {};
      route.paramNames.forEach((name, i) => {
        params[name] = decodeURIComponent(match[i + 1]);
      });

      // Clear content and render
      contentEl.innerHTML = '';
      try {
        await route.handler(contentEl, params);
        currentDestroy = route.destroy || null;
        currentModule = route.pageModule || null;
      } catch (err) {
        contentEl.innerHTML = `
          <div class="content-body">
            <div class="error-box">
              <h3>Page Error</h3>
              <p>${escapeHtml(err.message)}</p>
            </div>
          </div>`;
        console.error('Route error:', err);
      }

      // Scroll to top after rendering
      contentEl.scrollTop = 0;

      // Update sidebar active state
      updateSidebarActive(path);
      return;
    }
  }

  // No match — show 404
  contentEl.innerHTML = `
    <div class="content-body">
      <div class="empty-state">
        <div class="empty-icon">404</div>
        <div class="empty-title">Page not found</div>
        <div class="empty-description">The page "${escapeHtml(path)}" doesn't exist.</div>
        <button class="btn" onclick="window.location.hash='#/'">Go to Dashboard</button>
      </div>
    </div>`;

  // Scroll to top for 404 as well
  contentEl.scrollTop = 0;
}

function updateSidebarActive(path) {
  document.querySelectorAll('.sidebar-item').forEach(item => {
    const href = item.dataset.route || '';
    // Match exact or prefix (e.g. /entities matches /entities/abc)
    const isActive = path === href || (href !== '/' && path.startsWith(href + '/'));
    item.classList.toggle('active', isActive);
  });
}

function escapeHtml(s) {
  const d = document.createElement('div');
  d.textContent = s || '';
  return d.innerHTML;
}
