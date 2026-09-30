import React, { useState } from 'react';
import { Copy, Check } from 'lucide-react';
import { useToast } from '@/shared/components/Toast';

export interface CopyTableButtonProps {
  getData: () => string;
  disabled?: boolean;
  label?: string;
  className?: string;
}

export const CopyTableButton: React.FC<CopyTableButtonProps> = ({
  getData,
  disabled = false,
  label = '复制表格数据',
  className = 'btn btn-outline btn-sm',
}) => {
  const [copied, setCopied] = useState(false);
  const { showSuccess, showError } = useToast();

  const handleCopy = async () => {
    try {
      const text = getData();
      if (!text) return;
      await navigator.clipboard.writeText(text);
      setCopied(true);
      showSuccess('表格数据已复制为 TSV，可直接粘贴到 Excel 或飞书');
      setTimeout(() => setCopied(false), 2000);
    } catch (err: any) {
      showError('复制失败: ' + (err?.message || '请手动复制'));
    }
  };

  return (
    <button
      type='button'
      className={className}
      disabled={disabled}
      onClick={handleCopy}
      title='以制表符分隔格式 (TSV) 复制数据'
    >
      {copied ? <Check size={14} color='#16a34a' /> : <Copy size={14} />}
      <span style={{ marginLeft: '4px' }}>{copied ? '已复制' : label}</span>
    </button>
  );
};
