import React from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';

export interface PaginationProps {
  page: number;
  totalPages: number;
  total: number;
  onPageChange: (page: number) => void;
}

export const Pagination: React.FC<PaginationProps> = ({ page, totalPages, total, onPageChange }) => {
  if (total <= 0) return null;

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '12px 16px',
        borderTop: '1px solid #f1f5f9',
        fontSize: '13px',
        color: '#64748b',
      }}
    >
      <span>共 {total} 条记录，第 {page} / {Math.max(totalPages, 1)} 页</span>
      <div style={{ display: 'flex', gap: '8px' }}>
        <button
          disabled={page <= 1}
          onClick={() => onPageChange(page - 1)}
          style={{
            padding: '4px 8px',
            border: '1px solid #cbd5e1',
            borderRadius: '4px',
            backgroundColor: '#ffffff',
            cursor: page <= 1 ? 'not-allowed' : 'pointer',
            opacity: page <= 1 ? 0.5 : 1,
            display: 'flex',
            alignItems: 'center',
          }}
        >
          <ChevronLeft size={16} /> 上一页
        </button>
        <button
          disabled={page >= totalPages}
          onClick={() => onPageChange(page + 1)}
          style={{
            padding: '4px 8px',
            border: '1px solid #cbd5e1',
            borderRadius: '4px',
            backgroundColor: '#ffffff',
            cursor: page >= totalPages ? 'not-allowed' : 'pointer',
            opacity: page >= totalPages ? 0.5 : 1,
            display: 'flex',
            alignItems: 'center',
          }}
        >
          下一页 <ChevronRight size={16} />
        </button>
      </div>
    </div>
  );
};

