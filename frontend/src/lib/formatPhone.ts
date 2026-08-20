// Phone numbers are stored as whatever the user typed (no format enforced on
// input) - this only reformats display, it never touches what's saved.
export function formatPhone(raw: string | null | undefined): string {
  if (!raw) return ''

  let digits = raw.replace(/\D/g, '')
  if (digits.length === 11 && digits.startsWith('1')) {
    digits = digits.slice(1)
  }

  // Anything that isn't a standard 10-digit US number (extensions,
  // international numbers, partial input, etc.) is shown as typed rather
  // than mangled into a shape that doesn't fit it.
  if (digits.length !== 10) return raw

  return `(${digits.slice(0, 3)}) ${digits.slice(3, 6)}-${digits.slice(6)}`
}
