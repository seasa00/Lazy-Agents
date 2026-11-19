// Reusable redaction helper. Everything the Inspector renders goes through this, so a future
// backend adapter cannot accidentally leak credentials into the UI.
const RULES = [
  [/\b(?:sk|rk|pk)-[A-Za-z0-9_-]{8,}\b/g, '[REDACTED_KEY]'],
  [/\bAKIA[0-9A-Z]{12,}\b/g, '[REDACTED_AWS_KEY]'],
  [/\bgh[pousr]_[A-Za-z0-9]{16,}\b/g, '[REDACTED_TOKEN]'],
  [/\bBearer\s+[A-Za-z0-9._~+/=-]{8,}/gi, 'Bearer [REDACTED]'],
  [/\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{4,}\b/g, '[REDACTED_JWT]'],
  [/(:\/\/[^\s:@/]+:)([^@\s/]+)(@)/g, '$1[REDACTED]$3'], // credentials inside URLs
  [/((?:api[_-]?key|secret|token|passw(?:or)?d|pwd|authorization|private[_-]?key|access[_-]?key|client[_-]?secret)["']?\s*[:=]\s*["']?)(?!\[REDACTED)([^\s"',}]+)/gi, '$1[REDACTED]'],
]
const SECRET_KEY = /(api[_-]?key|secret|token|passw(or)?d|pwd|authorization|private[_-]?key|access[_-]?key|credential)/i

export function redactText(input) {
  if (typeof input !== 'string' || !input) return { text: input ?? '', count: 0 }
  let text = input, count = 0
  for (const [re, rep] of RULES) text = text.replace(re, (...m) => { count++; return rep.replace(/\$(\d)/g, (_, i) => m[+i] ?? '') })
  return { text, count }
}
export const safe = (s) => redactText(s).text

// Deep copy with every string redacted and secret-looking keys masked outright.
export function redactDeep(value, stats = { count: 0 }) {
  const walk = (v, key = '') => {
    if (typeof v === 'string') {
      if (SECRET_KEY.test(key) && v && !v.startsWith('[REDACTED')) { stats.count++; return '[REDACTED]' }
      const r = redactText(v); stats.count += r.count; return r.text
    }
    if (Array.isArray(v)) return v.map((x) => walk(x, key))
    if (v && typeof v === 'object') return Object.fromEntries(Object.entries(v).map(([k, x]) => [k, walk(x, k)]))
    return v
  }
  const out = walk(value)
  return { value: out, redactions: stats.count }
}
