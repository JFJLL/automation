import React from 'react';

export interface BadgeProps {
  status?: string;
  label?: string;
  style?: React.CSSProperties;
}

export const StatusBadge: React.FC<BadgeProps> = ({ status = 'unknown', label, style }) => {
  const norm = status.toLowerCase();
  
  const map: Record<string, { bg: string; text: string; label: string }> = {
    success: { bg: '#ecfdf5', text: '#059669', label: '成功' },
    running: { bg: '#eff6ff', text: '#2563eb', label: '运行中' },
    failed: { bg: '#fef2f2', text: '#dc2626', label: '失败' },
    active: { bg: '#f0fdf4', text: '#16a34a', label: '正常生效' },
    paused: { bg: '#fefce8', text: '#ca8a04', label: '已暂停' },
    archived: { bg: '#f1f5f9', text: '#64748b', label: '已归档' },
    partial: { bg: '#fff7ed', text: '#ea580c', label: '部分成功' },
    empty: { bg: '#f8fafc', text: '#64748b', label: '暂无数据' },
  };

  const conf = map[norm] || { bg: '#f1f5f9', text: '#475569', label: norm };

  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        padding: '3px 8px',
        borderRadius: '9999px',
        fontSize: '12px',
        fontWeight: 500,
        backgroundColor: conf.bg,
        color: conf.text,
        lineHeight: 1.2,
        ...style,
      }}
    >
      {label || conf.label}
    </span>
  );
};

