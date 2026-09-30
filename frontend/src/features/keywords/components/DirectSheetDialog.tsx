import React from 'react';
import { ExternalLink, AlertTriangle } from 'lucide-react';
import { Dialog } from '@/shared/components/Dialog';
import { Button } from '@/shared/components/Button';

export interface DirectSheetDialogProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  setTitle: (val: string) => void;
  keywordsCount: number;
  startDate: string;
  endDate: string;
  hasFailedKeywords: boolean;
  onSubmit: () => void;
  isSubmitting: boolean;
  spreadsheetUrl?: string;
}

export const DirectSheetDialog: React.FC<DirectSheetDialogProps> = ({
  isOpen,
  onClose,
  title,
  setTitle,
  keywordsCount,
  startDate,
  endDate,
  hasFailedKeywords,
  onSubmit,
  isSubmitting,
  spreadsheetUrl,
}) => {
  return (
    <Dialog isOpen={isOpen} onClose={onClose} title="直接生成飞书表格" width="460px">
      <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
        {hasFailedKeywords && (
          <div
            style={{
              padding: '10px 14px',
              backgroundColor: '#fef2f2',
              border: '1px solid #fecaca',
              borderRadius: '6px',
              fontSize: '12px',
              color: '#dc2626',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
            }}
          >
            <AlertTriangle size={15} />
            <span>当前存在获取失败的关键词，为防止脏数据污染正式表格，建议先重试或移除失败词。</span>
          </div>
        )}

        <div>
          <label style={{ fontSize: '13px', fontWeight: 600, color: '#334155', display: 'block', marginBottom: '6px' }}>
            表格标题
          </label>
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            style={{
              width: '100%',
              padding: '9px 12px',
              borderRadius: '6px',
              border: '1px solid #cbd5e1',
              fontSize: '14px',
            }}
          />
        </div>

        <div style={{ fontSize: '13px', color: '#64748b' }}>
          写入 <strong>{keywordsCount}</strong> 个关键词，时间跨度：{startDate} 至 {endDate}。
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
          <Button variant="secondary" type="button" onClick={onClose}>
            取消
          </Button>
          <Button
            variant="primary"
            type="button"
            loading={isSubmitting}
            disabled={!title.trim() || hasFailedKeywords}
            onClick={onSubmit}
          >
            立即生成
          </Button>
        </div>

        {spreadsheetUrl && spreadsheetUrl.startsWith('https://') && (
          <div
            style={{
              marginTop: '8px',
              padding: '12px',
              backgroundColor: '#f0fdf4',
              border: '1px solid #bbf7d0',
              borderRadius: '8px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
            }}
          >
            <span style={{ fontSize: '13px', color: '#16a34a', fontWeight: 500 }}>飞书在线表格已生成！</span>
            <a
              href={spreadsheetUrl}
              target="_blank"
              rel="noreferrer"
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '4px',
                fontSize: '13px',
                fontWeight: 600,
                color: '#16a34a',
              }}
            >
              点击直达表格 <ExternalLink size={14} />
            </a>
          </div>
        )}
      </div>
    </Dialog>
  );
};

