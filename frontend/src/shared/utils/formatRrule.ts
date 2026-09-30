export function formatRruleText(rrule?: string): string {
  if (!rrule) return '-';
  const clean = rrule.replace(/^RRULE:/i, '').trim();
  const map: Record<string, string> = {
    'FREQ=DAILY;BYHOUR=12;BYMINUTE=30': '每天 12:30',
    'FREQ=DAILY;BYHOUR=9;BYMINUTE=0': '每天 09:00',
    'FREQ=DAILY;BYHOUR=18;BYMINUTE=0': '每天 18:00',
    'FREQ=WORKDAY;BYHOUR=10;BYMINUTE=0': '法定工作日 10:00',
    'FREQ=WORKDAY;BYHOUR=9;BYMINUTE=30': '法定工作日 09:30',
    'FREQ=DAILY;BYHOUR=13;BYMINUTE=30': '每天 13:30',
    'FREQ=WEEKLY;BYHOUR=9;BYMINUTE=0;BYDAY=MO,TU,WE,TH,FR': '工作日 09:00',
    'FREQ=WEEKLY;BYHOUR=13;BYMINUTE=30;BYDAY=MO,TU,WE,TH,FR': '错峰工作日 13:30',
  };
  if (map[clean]) return map[clean];

  if (clean.includes('BYDAY=MO,TU,WE,TH,FR') || clean.includes('WORKDAY=TRUE') || clean.includes('FREQ=WORKDAY')) {
    const hourMatch = clean.match(/BYHOUR=(\d+)/i);
    const minMatch = clean.match(/BYMINUTE=(\d+)/i);
    const h = hourMatch ? hourMatch[1].padStart(2, '0') : '09';
    const m = minMatch ? minMatch[1].padStart(2, '0') : '00';
    return `工作日 ${h}:${m}`;
  }

  const hourMatch = clean.match(/BYHOUR=(\d+)/i);
  const minMatch = clean.match(/BYMINUTE=(\d+)/i);
  let timeStr = '';
  if (hourMatch && minMatch) {
    timeStr = ` ${hourMatch[1].padStart(2, '0')}:${minMatch[1].padStart(2, '0')}`;
  } else if (hourMatch) {
    timeStr = ` ${hourMatch[1].padStart(2, '0')}:00`;
  }

  if (clean.startsWith('FREQ=DAILY')) return `每天${timeStr}`;
  if (clean.startsWith('FREQ=WEEKLY')) return `每周${timeStr}`;
  if (clean.startsWith('FREQ=MONTHLY')) return `每月${timeStr}`;
  return clean;
}

