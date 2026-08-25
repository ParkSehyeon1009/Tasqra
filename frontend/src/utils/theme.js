const THEME_STORAGE_KEY = 'tasqra-theme-color'
export const DEFAULT_THEME_COLOR = '#16234a'

export const THEME_PRESETS = [
  { name: '네이비', color: '#16234a' },
  { name: '딥바이올렛', color: '#1d1442' },
  { name: '딥블루', color: '#132d53' },
  { name: '포레스트', color: '#123c38' },
]

export function getSavedThemeColor() {
  const saved = localStorage.getItem(THEME_STORAGE_KEY)
  return /^#[0-9a-f]{6}$/i.test(saved ?? '') ? saved : DEFAULT_THEME_COLOR
}

export function applyThemeColor(color) {
  const normalized = /^#[0-9a-f]{6}$/i.test(color) ? color.toLowerCase() : DEFAULT_THEME_COLOR
  const base = hexToHsl(normalized)
  const root = document.documentElement
  const set = (name, value) => root.style.setProperty(name, value)

  // 선택색은 강조 카드의 시작점이다. 나머지는 모든 테마에서 같은 명도 규칙으로 만든다.
  const isNeutral = base.s < 2
  const heroTo = hslToHex({ ...base, l: clamp(base.l > 72 ? base.l - 8 : base.l + 10, 0, 100) })
  const railFrom = hslToHex({ ...base, l: clamp(base.l - 7, 0, 100) })
  const railTo = hslToHex({ ...base, l: clamp(base.l > 72 ? base.l - 3 : base.l + 3, 0, 100) })
  const accent = isNeutral ? hslToHex({ h: 220, s: 12, l: base.l > 70 ? 38 : 62 }) : hslToHex({ h: base.h, s: clamp(base.s + 14, 58, 82), l: base.l > 78 ? 42 : 52 })
  const accentStrong = isNeutral ? hslToHex({ h: 220, s: 12, l: base.l > 70 ? 28 : 72 }) : hslToHex({ h: base.h, s: clamp(base.s + 14, 58, 82), l: base.l > 78 ? 32 : 42 })
  const accentRgb = hexToRgb(accent)

  set('--tasqra-hero-from', normalized)
  set('--tasqra-hero-to', heroTo)
  set('--tasqra-hero-glow', `rgba(${accentRgb.r}, ${accentRgb.g}, ${accentRgb.b}, .30)`)
  set('--tasqra-rail', railFrom)
  set('--tasqra-rail-end', railTo)
  set('--c-accent', accent)
  set('--c-accent-strong', accentStrong)
  set('--c-accent-soft', isNeutral ? (base.l > 70 ? '#eef0f3' : '#e7e9ed') : `hsla(${base.h}, 80%, 96%, 1)`)
  set('--c-accent-bg', `rgba(${accentRgb.r}, ${accentRgb.g}, ${accentRgb.b}, .09)`)
  set('--c-accent-border', `rgba(${accentRgb.r}, ${accentRgb.g}, ${accentRgb.b}, .28)`)
  set('--tasqra-rail-active', `rgba(${accentRgb.r}, ${accentRgb.g}, ${accentRgb.b}, .18)`)
  set('--tasqra-rail-text', readableText(railFrom))
  set('--tasqra-rail-muted', readableMutedText(railFrom))
  set('--tasqra-on-hero', readableText(normalized))
  set('--tasqra-on-hero-muted', readableMutedText(normalized))
  set('--tasqra-hero-line', readableOverlay(normalized, .13))
  set('--tasqra-hero-fill', readableOverlay(normalized, .12))
  localStorage.setItem(THEME_STORAGE_KEY, normalized)
  return normalized
}

function hexToRgb(hex) {
  const value = Number.parseInt(hex.slice(1), 16)
  return { r: value >> 16, g: (value >> 8) & 255, b: value & 255 }
}

export function hexToHsl(hex) {
  let { r, g, b } = hexToRgb(hex)
  r /= 255; g /= 255; b /= 255
  const max = Math.max(r, g, b), min = Math.min(r, g, b)
  const l = (max + min) / 2
  const delta = max - min
  if (!delta) return { h: 0, s: 0, l: Math.round(l * 100) }
  const s = delta / (1 - Math.abs(2 * l - 1))
  let h = max === r ? ((g - b) / delta) % 6 : max === g ? (b - r) / delta + 2 : (r - g) / delta + 4
  h = Math.round(h * 60)
  if (h < 0) h += 360
  return { h, s: Math.round(s * 100), l: Math.round(l * 100) }
}

export function hslToHex({ h, s, l }) {
  s /= 100; l /= 100
  const c = (1 - Math.abs(2 * l - 1)) * s
  const x = c * (1 - Math.abs((h / 60) % 2 - 1))
  const m = l - c / 2
  const [r, g, b] = h < 60 ? [c,x,0] : h < 120 ? [x,c,0] : h < 180 ? [0,c,x] : h < 240 ? [0,x,c] : h < 300 ? [x,0,c] : [c,0,x]
  return '#' + [r,g,b].map(value => Math.round((value + m) * 255).toString(16).padStart(2, '0')).join('')
}

function clamp(value, min, max) { return Math.min(max, Math.max(min, value)) }

function relativeLuminance(hex) {
  const values = Object.values(hexToRgb(hex)).map(value => {
    value /= 255
    return value <= .03928 ? value / 12.92 : ((value + .055) / 1.055) ** 2.4
  })
  return .2126 * values[0] + .7152 * values[1] + .0722 * values[2]
}

function readableText(background) { return relativeLuminance(background) > .48 ? '#111827' : '#ffffff' }
function readableMutedText(background) { return relativeLuminance(background) > .48 ? 'rgba(17,24,39,.66)' : 'rgba(255,255,255,.64)' }
function readableOverlay(background, alpha) { return relativeLuminance(background) > .48 ? `rgba(17,24,39,${alpha})` : `rgba(255,255,255,${alpha})` }
