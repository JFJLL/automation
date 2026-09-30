import React from 'react';
import { AlertTriangle, CheckSquare, Square } from 'lucide-react';

export interface SheetSelectorProps {
  sheets: any[];
  selectedSheetIndices: number[];
  onToggleSheet: (idx: number) => void;
  selectedPlatform: string;
}

export const SheetSelector: React.FC<SheetSelectorProps> = ({
  sheets,
  selectedSheetIndices,
  onToggleSheet,
  selectedPlatform,
}) => {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
      <div style={{ fontSize: '13px', color: '#475569', fontWeight: 600 }}>
        可多选同步的工作表 ({selectedSheetIndices.length} / {sheets.length} 已勾选):
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '12px' }}>
        {sheets.map((s, idx) => {
          const isSelected = selectedSheetIndices.includes(idx);
          const isMismatch = s.detected_platform && s.detected_platform !== selectedPlatform;

          return (
            <div
              key={s.sheet_title}
              onClick={() => onToggleSheet(idx)}
              style={{
                padding: '14px 16px',
                borderRadius: '8px',
                border: '1.5px solid ' + (isSelected ? '#ea3445' : '#e2e8f0'),
                backgroundColor: isSelected ? '#fef2f2' : '#ffffff',
                cursor: 'pointer',
                display: 'flex',
                flexDirection: 'column',
                gap: '8px',
                transition: 'all 0.15s ease',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <span style={{ fontWeight: 600, fontSize: '14px', color: isSelected ? '#ea3445' : '#0f172a' }}>
                  {s.sheet_title}
                </span>
                {isSelected ? <CheckSquare size={18} color="#ea3445" /> : <Square size={18} color="#94a3b8" />}
              </div>

              <div style={{ fontSize: '12px', color: '#64748b', display: 'flex', flexDirection: 'column', gap: '2px' }}>
                <div>ID列: <strong>{s.id_column || '未识别'}</strong> | 日期: <strong>{s.date_column || '未识别'}</strong></div>
                <div>识别实体: <strong>{s.detected_entity_ids?.length || 0} 个</strong></div>
              </div>

              {isMismatch && (
                <div
                  style={{
                    fontSize: '11px',
                    color: '#c2410c',
                    backgroundColor: '#fff7ed',
                    padding: '4px 8px',
                    borderRadius: '4px',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '4px',
                  }}
                >
                  <AlertTriangle size={12} />
                  <span>表头可能属于【{s.detected_platform === 'jzt' ? '京准通' : s.detected_platform === 'taobao' ? '淘宝' : '聚光'}】</span>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

