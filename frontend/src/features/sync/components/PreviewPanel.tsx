import React from 'react';
import { Eye, AlertCircle, CheckCircle } from 'lucide-react';
import { Button } from '@/shared/components/Button';

export interface PreviewPanelProps {
  onFetchPreview: () => void;
  isLoading: boolean;
  previewResult?: {
    headers: string[];
    rows: any[][];
    total_fetched: number;
    errors?: string[];
  };
}

export const PreviewPanel: React.FC<PreviewPanelProps> = ({
  onFetchPreview,
  isLoading,
  previewResult,
}) => {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '14px', marginTop: '10px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ fontSize: '13px', color: '#475569', fontWeight: 600 }}>
          平台真实数据抓取测试与预览 (Preview)
        </div>
        <Button size="sm" variant="secondary" onClick={onFetchPreview} loading={isLoading}>
          <Eye size={14} /> 拉取最新数据预览
        </Button>
      </div>

      {previewResult && (
        <div style={{ backgroundColor: '#f8fafc', borderRadius: '8px', border: '1px solid #e2e8f0', padding: '14px' }}>
          {previewResult.errors && previewResult.errors.length > 0 && (
            <div
              style={{
                padding: '8px 12px',
                backgroundColor: '#fef2f2',
                borderRadius: '6px',
                color: '#dc2626',
                fontSize: '12px',
                marginBottom: '10px',
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
              }}
            >
              <AlertCircle size={14} />
              <span>部分实体拉取警告: {previewResult.errors.join('; ')}</span>
            </div>
          )}

          <div style={{ fontSize: '12px', color: '#64748b', marginBottom: '8px' }}>
            成功抓取前 <strong>{previewResult.rows.length}</strong> 行示例真实数据：
          </div>

          <div style={{ overflowX: 'auto', maxHeight: '240px' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px', textAlign: 'left' }}>
              <thead>
                <tr style={{ backgroundColor: '#edf2f7', borderBottom: '1px solid #cbd5e1' }}>
                  {previewResult.headers.map((h, i) => (
                    <th key={i} style={{ padding: '6px 10px', fontWeight: 600, color: '#334155', whiteSpace: 'nowrap' }}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {previewResult.rows.slice(0, 10).map((row, rIdx) => (
                  <tr key={rIdx} style={{ borderBottom: '1px solid #e2e8f0', backgroundColor: '#ffffff' }}>
                    {row.map((cell, cIdx) => (
                      <td key={cIdx} style={{ padding: '6px 10px', whiteSpace: 'nowrap', color: '#0f172a' }}>
                        {cell !== null && cell !== undefined ? String(cell) : '-'}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};

