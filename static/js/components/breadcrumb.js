// Breadcrumb Component
import { esc } from '../state.js';

/**
 * Render a breadcrumb trail.
 * @param {Array<{label, route?}>} items - last item has no route (current page)
 */
export function renderBreadcrumb(items) {
  return `<nav class="breadcrumb">${items.map((item, i) => {
    if (i < items.length - 1 && item.route) {
      return `<a href="#${item.route}">${esc(item.label)}</a><span class="separator">/</span>`;
    }
    return `<span>${esc(item.label)}</span>`;
  }).join('')}</nav>`;
}
