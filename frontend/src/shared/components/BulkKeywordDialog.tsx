import React, { useState, useEffect } from 'react';
import { Dialog } from '@/shared/components/Dialog';
import { Info, Trash2, Check, ArrowRight } from 'lucide-react';

export interface BulkKeywordDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: (keywords: string[]) => void;
  onConfirmAndSearch?: (keywords: string[]) => void;
  storageKey: string;
  initialKeywords?: string[];
  title?: string;
}

export const BulkKeywordDialog: React.FC<BulkKeywordDialogProps> = ({
  isOpen,
  onClose,
  onConfirm,
  onConfirmAndSearch,
  storageKey,
  initialKeywords = [],
  title = '批量输入关键词 (一行一个词)',
}) => {
  const [text, setText] = useState<string>(() => {
    try {
      const saved = localStorage.getItem(storageKey);
      if (saved !== null) return saved;
    } catch {}
    return initialKeywords.join('\n');
  });

  // 当打开弹窗时，如果本地存储有草稿则加载草稿；若无草稿且有初始关键词则填入
  useEffect(() => {
    if (isOpen) {
      try {
        const saved = localStorage.getItem(storageKey);
        if (saved !== null) {
          setText(saved);
        } else if (initialKeywords.length > 0 && !text) {
          setText(initialKeywords.join('\n'));
        }
      } catch {}
    }
  }, [isOpen, storageKey]);

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const val = e.target.value;
    setText(val);
    try {
      localStorage.setItem(storageKey, val);
    } catch {}
  };

  const handleClear = () => {
    setText('');
    try {
      localStorage.setItem(storageKey, '');
    } catch {}
  };

  // 严格按换行解析，每行独立为一个词，保留行内的逗号与空格
  const lines = text
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter(Boolean);
  const uniqueKeywords = Array.from(new Set(lines));

  const handleConfirm = () => {
    onConfirm(uniqueKeywords);
    onClose();
  };

  const handleConfirmAndSearch = () => {
    if (onConfirmAndSearch) {
      onConfirmAndSearch(uniqueKeywords);
    } else {
      onConfirm(uniqueKeywords);
    }
    onClose();
  };

  return (
    <Dialog isOpen={isOpen} onClose={onClose} title={title} width="600px">
      <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
        {/* 提示信息栏 */}
        <div
          style={{
            padding: '10px 14px',
            background: '#f0fdf4',
            border: '1px solid #bbf7d0',
            borderRadius: '8px',
            fontSize: '12px',
            color: '#166534',
            display: 'flex',
            alignItems: 'flex-start',
            gap: '8px',
            lineHeight: 1.5,
          }}
        >
          <Info size={16} style={{ flexShrink: 0, marginTop: '2px', color: '#16a34a' }} />
          <div>
            <strong>输入规则：</strong>每行作为一个独立关键词，支持直接从 Excel 或表格中复制整列粘贴。即使关键词内包含逗号、空格或特殊符号，整行内容均会完整保留作为关键词。
          </div>
        </div>

        {/* 计数与快捷操作 */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontSize: '13px', color: '#64748b' }}>
            已输入 <strong>{lines.length}</strong> 行，去重后共{' '}
            <strong style={{ color: 'var(--primary)' }}>{uniqueKeywords.length}</strong> 个有效关键词
          </span>
          {text.trim() && (
            <button
              type="button"
              onClick={handleClear}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '4px',
                fontSize: '12px',
                color: '#ef4444',
                background: 'none',
                border: 'none',
                cursor: 'pointer',
                padding: '2px 6px',
              }}
            >
              <Trash2 size={13} />
              清空内容
            </button>
          )}
        </div>

        {/* 文本输入框 */}
        <textarea
          value={text}
          onChange={handleChange}
          placeholder={'请输入或粘贴关键词，一行一个词，例如：\n凯乐石 冲锋衣\n新生儿干货, 测评\n耐克 跑鞋 42码\n户外登山防风外套'}
          rows={12}
          style={{
            width: '100%',
            padding: '12px 14px',
            fontSize: '13px',
            fontFamily: 'Consolas, Monaco, monospace, var(--font-family)',
            lineHeight: '1.6',
            border: '1.5px solid #cbd5e1',
            borderRadius: '8px',
            outline: 'none',
            resize: 'vertical',
            boxSizing: 'border-box',
            background: '#ffffff',
          }}
          onFocus={(e) => (e.target.style.borderColor = 'var(--primary)')}
          onBlur={(e) => (e.target.style.borderColor = '#cbd5e1')}
        />

        {/* 底部按钮栏 */}
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '6px' }}>
          <button type="button" className="btn btn-outline" onClick={onClose}>
            取消
          </button>
          <button
            type="button"
            className="btn btn-primary"
            disabled={uniqueKeywords.length === 0}
            onClick={handleConfirm}
          >
            <Check size={15} /> 确认 ({uniqueKeywords.length})
          </button>
          {onConfirmAndSearch && (
            <button
              type="button"
              className="btn btn-primary"
              style={{ background: 'var(--primary-dark, #dc2626)' }}
              disabled={uniqueKeywords.length === 0}
              onClick={handleConfirmAndSearch}
              title="应用关键词并立即触发数据查询"
            >
              确认并查询数据 <ArrowRight size={15} />
            </button>
          )}
        </div>
      </div>
    </Dialog>
  );
};
