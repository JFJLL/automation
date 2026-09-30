import React, { useState, useEffect } from 'react';
import { Dialog } from '@/shared/components/Dialog';

export interface CreateSheetDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (title: string) => Promise<void> | void;
  isPending: boolean;
  selectedWordsCount: number;
  dateRangeText?: string;
  defaultTitle?: string;
}

export const CreateSheetDialog: React.FC<CreateSheetDialogProps> = ({
  isOpen,
  onClose,
  onSubmit,
  isPending,
  selectedWordsCount,
  dateRangeText,
  defaultTitle = '',
}) => {
  const [title, setTitle] = useState(defaultTitle);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen) {
      setTitle(defaultTitle);
      setError(null);
    }
  }, [isOpen, defaultTitle]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const cleanTitle = title.trim();
    if (!cleanTitle || cleanTitle.length > 120) {
      setError('表格标题长度必须在 1 到 120 个字符之间');
      return;
    }
    if (selectedWordsCount < 1 || selectedWordsCount > 5000) {
      setError('关键词数量必须在 1 到 5000 个之间');
      return;
    }
    setError(null);
    onSubmit(cleanTitle);
  };

  return (
    <Dialog
      isOpen={isOpen}
      onClose={onClose}
      title='直接生成飞书表格'
      width='460px'
    >
      <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
        <div>
          <label style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text)', display: 'block', marginBottom: '6px' }}>
            表格标题 *
          </label>
          <input
            type='text'
            className='form-control'
            value={title}
            disabled={isPending}
            maxLength={120}
            onChange={(e) => { setTitle(e.target.value); setError(null); }}
          />
        </div>
        {dateRangeText && (
          <div style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
            写入 <strong>{selectedWordsCount}</strong> 个关键词，时间跨度：{dateRangeText}。
          </div>
        )}
        {error && (
          <div style={{ fontSize: '12px', color: '#dc2626', backgroundColor: '#fef2f2', padding: '6px 10px', borderRadius: '4px' }}>
            {error}
          </div>
        )}
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
          <button className='btn btn-outline' type='button' disabled={isPending} onClick={onClose}>
            取消
          </button>
          <button className='btn btn-primary' type='submit' disabled={isPending || !title.trim()}>
            {isPending ? '生成中...' : '确认生成并写入'}
          </button>
        </div>
      </form>
    </Dialog>
  );
};
