function pad(value: number): string {
  return String(value).padStart(2, '0');
}

export function parseBackendDateTime(value?: string | null): Date | null {
  const raw = String(value ?? '').trim();
  if (!raw) return null;
  const normalized = raw.includes('T') ? raw : raw.replace(' ', 'T');
  const hasTimezone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(normalized);
  const parsed = new Date(hasTimezone ? normalized : `${normalized}Z`);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

export function formatLocalDateTime(value?: string | null): string {
  const parsed = parseBackendDateTime(value);
  if (!parsed) return value ?? '';
  return `${parsed.getFullYear()}-${pad(parsed.getMonth() + 1)}-${pad(parsed.getDate())} ${pad(parsed.getHours())}:${pad(parsed.getMinutes())}:${pad(parsed.getSeconds())}`;
}
