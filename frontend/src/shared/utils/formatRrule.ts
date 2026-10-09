export function formatRruleText(rrule?: string): string {
  if (!rrule) return '-';
  const clean = rrule.replace(/^RRULE:/i, '').trim();
  
  const hourMatch = clean.match(/BYHOUR=(\d+)/i);
  const minMatch = clean.match(/BYMINUTE=(\d+)/i);
  const h = hourMatch ? hourMatch[1].padStart(2, '0') : '09';
  const m = minMatch ? minMatch[1].padStart(2, '0') : '00';
  const timeStr = `${h}:${m}`;

  const dayMap: Record<string, string> = {
    MO: '周一',
    TU: '周二',
    WE: '周三',
    TH: '周四',
    FR: '周五',
    SA: '周六',
    SU: '周日',
  };

  if (clean.includes('FREQ=WORKDAY') || clean.includes('WORKDAY=TRUE')) {
    return `工作日 ${timeStr}`;
  }

  if (clean.includes('FREQ=WEEKLY')) {
    const bydayMatch = clean.match(/BYDAY=([A-Z,]+)/i);
    if (bydayMatch) {
      const days = bydayMatch[1].split(',').map((d) => d.trim()).filter(Boolean);
      if (days.join(',') === 'MO,TU,WE,TH,FR') {
        return `工作日 ${timeStr}`;
      }
      const cnDays = days.map((d) => dayMap[d] || d).join('、');
      return `每${cnDays} ${timeStr}`;
    }
    return `每周 ${timeStr}`;
  }

  if (clean.includes('FREQ=DAILY')) {
    return `每天 ${timeStr}`;
  }

  return clean;
}
