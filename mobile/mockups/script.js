const preference = document.querySelector('#appearance');
const system = window.matchMedia('(prefers-color-scheme: dark)');
try { preference.value = localStorage.getItem('fitops.mockup.theme') || 'system'; } catch { /* File previews may block storage. */ }
if (!['system', 'dark', 'light'].includes(preference.value)) preference.value = 'system';
function applyTheme() {
  document.documentElement.dataset.theme = preference.value === 'system' ? (system.matches ? 'dark' : 'light') : preference.value;
}
preference.addEventListener('change', () => {
  try { localStorage.setItem('fitops.mockup.theme', preference.value); } catch { /* Session-only preference still works. */ }
  applyTheme();
});
system.addEventListener('change', applyTheme);
applyTheme();
document.querySelectorAll('nav button').forEach(button => button.addEventListener('click', () => {
  document.querySelectorAll('main section').forEach(section => { section.hidden = section.id !== button.dataset.screen; });
  document.querySelectorAll('nav button').forEach(item => item.removeAttribute('aria-current'));
  button.setAttribute('aria-current', 'page');
  document.querySelector('#current-screen').textContent = button.dataset.screen === 'zones' ? 'HR zones' : button.dataset.screen[0].toUpperCase() + button.dataset.screen.slice(1);
  document.querySelector('.navigation').open = false;
  document.querySelector(`#${button.dataset.screen} h1`).focus();
  window.scrollTo(0, 0);
}));

const navigation = document.querySelector('.navigation');
document.addEventListener('click', event => {
  if (!navigation.contains(event.target)) navigation.open = false;
});
document.addEventListener('keydown', event => {
  if (event.key === 'Escape' && navigation.open) {
    navigation.open = false;
    navigation.querySelector('summary').focus();
  }
});

// Subtle specular movement on pointer-capable devices; touch uses the static highlight.
const header = document.querySelector('.glass-header');
const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
header.addEventListener('pointermove', event => {
  if (event.pointerType !== 'mouse' || reducedMotion.matches) return;
  const bounds = header.getBoundingClientRect();
  const position = Math.max(0, Math.min(100, (event.clientX - bounds.left) / bounds.width * 100));
  header.style.setProperty('--glint-x', `${position}%`);
});
header.addEventListener('pointerleave', () => header.style.removeProperty('--glint-x'));
reducedMotion.addEventListener('change', () => header.style.removeProperty('--glint-x'));
