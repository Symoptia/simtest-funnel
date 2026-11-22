// Two tabs: "Synthetic signals" (default) and "Real weather" (#weather).
// Each panel is built the first time it is shown, so its plots are laid out
// while visible.

import { renderSynthetic } from './synthetic';

type TabId = 'synthetic' | 'weather';

const built = new Set<TabId>();

function tabFromHash(): TabId {
  return window.location.hash === '#weather' ? 'weather' : 'synthetic';
}

function build(tab: TabId): void {
  if (built.has(tab)) {
    return;
  }
  built.add(tab);
  if (tab === 'synthetic') {
    void renderSynthetic();
    return;
  }
  const panel = document.getElementById('weather');
  if (panel) {
    void import('./weather/ui').then((m) => m.mountWeather(panel));
  }
}

function show(tab: TabId): void {
  for (const button of document.querySelectorAll<HTMLButtonElement>(
    '[role="tab"]',
  )) {
    const selected = button.dataset.tab === tab;
    button.setAttribute('aria-selected', String(selected));
    button.tabIndex = selected ? 0 : -1;
  }
  for (const panel of document.querySelectorAll<HTMLElement>(
    '[role="tabpanel"]',
  )) {
    panel.hidden = panel.dataset.tab !== tab;
  }
  build(tab);
}

function setUp(): void {
  const tabs = [
    ...document.querySelectorAll<HTMLButtonElement>('[role="tab"]'),
  ];
  for (const button of tabs) {
    button.addEventListener('click', () => {
      const tab = button.dataset.tab === 'weather' ? 'weather' : 'synthetic';
      // replaceState keeps the scroll position and adds no history entry.
      history.replaceState(
        null,
        '',
        tab === 'weather' ? '#weather' : location.pathname + location.search,
      );
      show(tab);
    });
    button.addEventListener('keydown', (e) => {
      if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') {
        return;
      }
      const next = tabs[(tabs.indexOf(button) + 1) % tabs.length];
      next.focus();
      next.click();
    });
  }
  window.addEventListener('hashchange', () => show(tabFromHash()));
  show(tabFromHash());
}

setUp();
