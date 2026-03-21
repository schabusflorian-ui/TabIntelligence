// DebtFund SVG Icon System
// Minimal, stroke-based icons for sidebar navigation.
// Each returns an SVG string: 13x13 viewBox, 1.5px stroke, currentColor.

/** Dashboard — simple grid/house icon */
export function iconDashboard() {
  return `<svg width="13" height="13" viewBox="0 0 13 13" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
    <rect x="1.5" y="1.5" width="4" height="4" rx="0.5"/>
    <rect x="7.5" y="1.5" width="4" height="4" rx="0.5"/>
    <rect x="1.5" y="7.5" width="4" height="4" rx="0.5"/>
    <rect x="7.5" y="7.5" width="4" height="4" rx="0.5"/>
  </svg>`;
}

/** Extractions — upload/arrow-up icon */
export function iconExtractions() {
  return `<svg width="13" height="13" viewBox="0 0 13 13" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
    <line x1="6.5" y1="2.5" x2="6.5" y2="10.5"/>
    <polyline points="3.5,5.5 6.5,2.5 9.5,5.5"/>
  </svg>`;
}

/** Entities — building/company icon */
export function iconEntities() {
  return `<svg width="13" height="13" viewBox="0 0 13 13" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
    <rect x="2.5" y="1.5" width="8" height="10" rx="0.5"/>
    <line x1="5" y1="4" x2="5" y2="4.01"/>
    <line x1="8" y1="4" x2="8" y2="4.01"/>
    <line x1="5" y1="6.5" x2="5" y2="6.51"/>
    <line x1="8" y1="6.5" x2="8" y2="6.51"/>
    <rect x="5" y="9" width="3" height="2.5"/>
  </svg>`;
}

/** Taxonomy — tree/hierarchy icon */
export function iconTaxonomy() {
  return `<svg width="13" height="13" viewBox="0 0 13 13" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
    <line x1="6.5" y1="1.5" x2="6.5" y2="5"/>
    <line x1="6.5" y1="5" x2="3" y2="5"/>
    <line x1="6.5" y1="5" x2="10" y2="5"/>
    <line x1="3" y1="5" x2="3" y2="8.5"/>
    <line x1="10" y1="5" x2="10" y2="8.5"/>
    <line x1="6.5" y1="5" x2="6.5" y2="8.5"/>
    <circle cx="6.5" cy="1.5" r="0.01"/>
    <circle cx="3" cy="9.5" r="1"/>
    <circle cx="6.5" cy="9.5" r="1"/>
    <circle cx="10" cy="9.5" r="1"/>
  </svg>`;
}

/** Analytics — bar chart icon */
export function iconAnalytics() {
  return `<svg width="13" height="13" viewBox="0 0 13 13" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
    <line x1="2" y1="11" x2="11" y2="11"/>
    <line x1="3.5" y1="11" x2="3.5" y2="7"/>
    <line x1="6.5" y1="11" x2="6.5" y2="4"/>
    <line x1="9.5" y1="11" x2="9.5" y2="2"/>
  </svg>`;
}

/** Comparison — columns/scale icon */
export function iconComparison() {
  return `<svg width="13" height="13" viewBox="0 0 13 13" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
    <line x1="2" y1="1.5" x2="2" y2="11.5"/>
    <line x1="6.5" y1="1.5" x2="6.5" y2="11.5"/>
    <line x1="11" y1="1.5" x2="11" y2="11.5"/>
    <line x1="2" y1="4" x2="6.5" y2="4"/>
    <line x1="6.5" y1="7" x2="11" y2="7"/>
    <line x1="2" y1="9" x2="11" y2="9"/>
  </svg>`;
}

/** System — gear/settings icon */
export function iconBenchmarks() {
  return `<svg width="13" height="13" viewBox="0 0 13 13" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
    <path d="M1.5 11.5h10M3 11.5V7M6.5 11.5V4M10 11.5V1.5"/>
  </svg>`;
}

export function iconSystem() {
  return `<svg width="13" height="13" viewBox="0 0 13 13" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
    <circle cx="6.5" cy="6.5" r="2"/>
    <path d="M6.5 1v1.2M6.5 10.8v1.2M1 6.5h1.2M10.8 6.5H12M2.6 2.6l.85.85M9.55 9.55l.85.85M10.4 2.6l-.85.85M3.45 9.55l-.85.85"/>
  </svg>`;
}
