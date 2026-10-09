import React, { useState, useEffect, useRef } from 'react';
import { Clock, ChevronDown, Check } from 'lucide-react';

export interface SchedulePickerProps {
  value: string;
  onChange: (rrule: string) => void;
  style?: React.CSSProperties;
  label?: string;
}

const WEEKDAYS = [
  { key: 'MO', label: '周一' },
  { key: 'TU', label: '周二' },
  { key: 'WE', label: '周三' },
  { key: 'TH', label: '周四' },
  { key: 'FR', label: '周五' },
  { key: 'SA', label: '周六' },
  { key: 'SU', label: '周日' },
];

// 生成从 00:00 到 23:45，每 15 分钟为一个选项 (共 96 个项)
const TIME_OPTIONS: string[] = [];
for (let h = 0; h < 24; h++) {
  for (let m = 0; m < 60; m += 15) {
    TIME_OPTIONS.push(`${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`);
  }
}

/**
 * 自定义单列长列表滚动时间下拉组件：
 * 选项菜单宽度与上方触发按钮 100% 等宽严格对齐
 */
const CustomTimeDropdown: React.FC<{
  value: string;
  onChange: (val: string) => void;
}> = ({ value, onChange }) => {
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  // 点击外部自动关闭
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isOpen]);

  // 打开下拉框时自动定位滚动到当前选中的项
  useEffect(() => {
    if (isOpen && listRef.current) {
      const selectedEl = listRef.current.querySelector('[data-selected="true"]') as HTMLElement | null;
      if (selectedEl) {
        listRef.current.scrollTop = selectedEl.offsetTop - listRef.current.offsetTop;
      }
    }
  }, [isOpen]);

  return (
    <div ref={containerRef} style={{ position: 'relative', width: '130px', flexShrink: 0 }}>
      {/* 触发框：固定 130px 宽度，右对齐下拉箭头 */}
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        style={{
          width: '100%',
          height: '36px',
          padding: '0 10px',
          fontSize: '13px',
          fontWeight: 600,
          color: '#1e293b',
          background: '#ffffff',
          border: isOpen ? '1px solid #f53f3f' : '1px solid #cbd5e1',
          borderRadius: '6px',
          cursor: 'pointer',
          outline: 'none',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          boxShadow: isOpen ? '0 0 0 2px rgba(245, 63, 63, 0.15)' : 'none',
          boxSizing: 'border-box',
          transition: 'all .15s ease',
        }}
      >
        <span>{value}</span>
        <ChevronDown
          size={14}
          style={{
            color: '#64748b',
            transform: isOpen ? 'rotate(180deg)' : 'none',
            transition: 'transform .2s ease',
          }}
        />
      </button>

      {/* 浮动下拉弹层：宽度 100% 严格与上方按钮完全对齐，原本单列长列表滚动 */}
      {isOpen && (
        <div
          ref={listRef}
          style={{
            position: 'absolute',
            top: 'calc(100% + 4px)',
            left: 0,
            width: '100%',
            boxSizing: 'border-box',
            maxHeight: '210px',
            overflowY: 'auto',
            background: '#ffffff',
            border: '1px solid #e2e8f0',
            borderRadius: '6px',
            boxShadow: '0 6px 20px rgba(15, 23, 42, 0.12)',
            zIndex: 1050,
            padding: '4px 0',
            display: 'flex',
            flexDirection: 'column',
          }}
        >
          {TIME_OPTIONS.map((t) => {
            const isSelected = t === value;
            return (
              <div
                key={t}
                data-selected={isSelected}
                onClick={() => {
                  onChange(t);
                  setIsOpen(false);
                }}
                style={{
                  padding: '7px 12px',
                  fontSize: '13px',
                  fontWeight: isSelected ? 600 : 400,
                  color: isSelected ? '#f53f3f' : '#334155',
                  background: isSelected ? '#fff0f0' : 'transparent',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  transition: 'background .12s ease',
                  boxSizing: 'border-box',
                }}
                onMouseEnter={(e) => {
                  if (!isSelected) {
                    (e.currentTarget as HTMLElement).style.background = '#f1f5f9';
                  }
                }}
                onMouseLeave={(e) => {
                  if (!isSelected) {
                    (e.currentTarget as HTMLElement).style.background = 'transparent';
                  }
                }}
              >
                <span>{t}</span>
                {isSelected && <Check size={13} style={{ color: '#f53f3f' }} />}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

export const SchedulePicker: React.FC<SchedulePickerProps> = ({
  value,
  onChange,
  style,
  label = '自动化同步周期 (RRULE)',
}) => {
  const parseRrule = (rruleStr: string) => {
    const clean = (rruleStr || '').replace(/^RRULE:/i, '').trim();
    let freq: 'daily' | 'workday' | 'weekly' = 'daily';
    if (clean.includes('FREQ=WORKDAY') || clean.includes('WORKDAY=TRUE')) {
      freq = 'workday';
    } else if (clean.includes('FREQ=WEEKLY')) {
      freq = 'weekly';
    }

    const hourMatch = clean.match(/BYHOUR=(\d+)/i);
    const minMatch = clean.match(/BYMINUTE=(\d+)/i);
    let h = hourMatch ? hourMatch[1].padStart(2, '0') : '09';
    let m = minMatch ? minMatch[1].padStart(2, '0') : '00';
    const mNum = parseInt(m, 10);
    const roundedM = Math.round(mNum / 15) * 15;
    m = String(roundedM >= 60 ? 45 : roundedM).padStart(2, '0');
    const timeVal = `${h}:${m}`;

    let days = ['MO'];
    const bydayMatch = clean.match(/BYDAY=([A-Z,]+)/i);
    if (bydayMatch) {
      days = bydayMatch[1].split(',').map((d) => d.trim()).filter(Boolean);
      if (days.length === 0) days = ['MO'];
    }
    return { freq, time: timeVal, days };
  };

  const initial = parseRrule(value);
  const [freq, setFreq] = useState<'daily' | 'workday' | 'weekly'>(initial.freq);
  const [time, setTime] = useState<string>(initial.time);
  const [selectedDays, setSelectedDays] = useState<string[]>(initial.days);
  const isInternalChange = useRef(false);

  useEffect(() => {
    if (isInternalChange.current) {
      isInternalChange.current = false;
      return;
    }
    const parsed = parseRrule(value);
    setFreq(parsed.freq);
    setTime(parsed.time);
    setSelectedDays(parsed.days);
  }, [value]);

  const emitChange = (newFreq: 'daily' | 'workday' | 'weekly', newTime: string, newDays: string[]) => {
    const [hStr, mStr] = (newTime || '09:00').split(':');
    const hour = parseInt(hStr || '9', 10);
    const minute = parseInt(mStr || '0', 10);

    let rruleResult = '';
    if (newFreq === 'daily') {
      rruleResult = `RRULE:FREQ=DAILY;BYHOUR=${hour};BYMINUTE=${minute}`;
    } else if (newFreq === 'workday') {
      rruleResult = `RRULE:FREQ=WORKDAY;BYHOUR=${hour};BYMINUTE=${minute}`;
    } else {
      const daysStr = newDays.length > 0 ? newDays.join(',') : 'MO';
      rruleResult = `RRULE:FREQ=WEEKLY;BYDAY=${daysStr};BYHOUR=${hour};BYMINUTE=${minute}`;
    }
    isInternalChange.current = true;
    onChange(rruleResult);
  };

  const handleFreqChange = (newFreq: 'daily' | 'workday' | 'weekly') => {
    setFreq(newFreq);
    emitChange(newFreq, time, selectedDays);
  };

  const handleTimeChange = (newTime: string) => {
    setTime(newTime);
    emitChange(freq, newTime, selectedDays);
  };

  const handleToggleDay = (dayKey: string) => {
    let nextDays: string[];
    if (selectedDays.includes(dayKey)) {
      if (selectedDays.length <= 1) return; // 至少保留一天
      nextDays = selectedDays.filter((d) => d !== dayKey);
    } else {
      nextDays = [...selectedDays, dayKey];
    }
    setSelectedDays(nextDays);
    emitChange(freq, time, nextDays);
  };

  const getSummary = () => {
    if (freq === 'daily') return `每天 ${time} 自动执行`;
    if (freq === 'workday') return `法定工作日 ${time} 自动执行`;
    const dayNameMap: Record<string, string> = {
      MO: '周一', TU: '周二', WE: '周三', TH: '周四', FR: '周五', SA: '周六', SU: '周日'
    };
    const daysStr = selectedDays.map((d) => dayNameMap[d] || d).join('、');
    return `每${daysStr} ${time} 自动执行`;
  };

  return (
    <div style={{ ...style }}>
      {label && (
        <label style={{ fontSize: '13px', fontWeight: 600, color: '#334155', display: 'block', marginBottom: '8px' }}>
          {label}
        </label>
      )}
      <div
        style={{
          background: '#f8fafc',
          border: '1px solid #e2e8f0',
          borderRadius: '8px',
          padding: '14px',
          display: 'flex',
          flexDirection: 'column',
          gap: '12px',
        }}
      >
        {/* 顶部行：周期分段单选 + 执行时间选择器，两端对齐且排在一行 */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px', flexWrap: 'nowrap' }}>
          {/* 分段单选控件 */}
          <div
            style={{
              display: 'inline-flex',
              background: '#edeef2',
              padding: '3px',
              borderRadius: '7px',
              border: '1px solid #e2e8f0',
              flexShrink: 0,
            }}
          >
            {(
              [
                { key: 'daily', label: '每天' },
                { key: 'workday', label: '工作日' },
                { key: 'weekly', label: '每周' },
              ] as const
            ).map((item) => {
              const active = freq === item.key;
              return (
                <button
                  key={item.key}
                  type="button"
                  onClick={() => handleFreqChange(item.key)}
                  style={{
                    padding: '6px 14px',
                    fontSize: '13px',
                    fontWeight: active ? 600 : 500,
                    color: active ? '#0f172a' : '#64748b',
                    background: active ? '#ffffff' : 'transparent',
                    borderRadius: '5px',
                    border: 'none',
                    boxShadow: active ? '0 1px 3px rgba(0, 0, 0, 0.08)' : 'none',
                    cursor: 'pointer',
                    transition: 'all .15s ease',
                  }}
                >
                  {item.label}
                </button>
              );
            })}
          </div>

          {/* 执行时间标签 + 130px 单列长列表下拉框 (宽度 100% 严格一致) */}
          <div style={{ display: 'inline-flex', alignItems: 'center', gap: '8px', flexShrink: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
              <Clock size={15} style={{ color: '#64748b' }} />
              <span style={{ fontSize: '13px', color: '#475569', fontWeight: 500, whiteSpace: 'nowrap' }}>执行时间</span>
            </div>
            <CustomTimeDropdown value={time} onChange={handleTimeChange} />
          </div>
        </div>

        {/* 每周时展示周一至周日复选按钮（7 列等宽对称排布） */}
        {freq === 'weekly' && (
          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              gap: '6px',
              paddingTop: '8px',
              borderTop: '1px dashed #e2e8f0',
            }}
          >
            <span style={{ fontSize: '12px', fontWeight: 600, color: '#475569' }}>
              更新星期（可多选）
            </span>
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(7, 1fr)',
                gap: '6px',
              }}
            >
              {WEEKDAYS.map((wd) => {
                const isSelected = selectedDays.includes(wd.key);
                return (
                  <button
                    key={wd.key}
                    type="button"
                    onClick={() => handleToggleDay(wd.key)}
                    style={{
                      height: '32px',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      fontSize: '12px',
                      borderRadius: '6px',
                      border: isSelected ? '1px solid #f53f3f' : '1px solid #cbd5e1',
                      background: isSelected ? '#f53f3f' : '#ffffff',
                      color: isSelected ? '#ffffff' : '#334155',
                      cursor: 'pointer',
                      fontWeight: isSelected ? 600 : 500,
                      boxShadow: isSelected ? '0 2px 4px rgba(245, 63, 63, 0.2)' : 'none',
                      transition: 'all .15s ease',
                    }}
                  >
                    {wd.label}
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {/* 底部调度说明卡片 */}
        <div
          style={{
            background: '#ffffff',
            border: '1px solid #e2e8f0',
            borderRadius: '6px',
            padding: '7px 10px',
            fontSize: '12px',
            color: '#64748b',
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
          }}
        >
          <span>💡 调度规则：</span>
          <strong style={{ color: '#0f172a' }}>{getSummary()}</strong>
        </div>
      </div>
    </div>
  );
};
