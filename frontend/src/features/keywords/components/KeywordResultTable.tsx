import React, { useState } from 'react';
import { AlertTriangle, ArrowUpDown, RefreshCw, AlertCircle } from 'lucide-react';
import { StatusBadge } from '@/shared/components/Badge';
import { Button } from '@/shared/components/Button';

export interface KeywordResultTableProps {
  queryResult: {
    success: boolean;
    overall_status: string;
    keywords: string[];
    start_date: string;
    end_date: string;
    dates: string[];
    data: Record<string, Record<string, any> | null>;
    keyword_statuses: Record<string, { status: string; error_message?: string }>;
    successful_keywords: string[];
    empty_keywords: string[];
    failed_keywords: string[];
  };
  onRetryFailed: (failedWords: string[]) => void;
  isRetrying: boolean;
}

export const KeywordResultTable: React.FC<KeywordResultTableProps> = ({
  queryResult,
  onRetryFailed,
  isRetrying,
}) => {
  const [isDescending, setIsDescending] = useState(true);

  const dates = React.useMemo(() => {
    return isDescending ? [...queryResult.dates].reverse() : queryResult.dates;
  }, [queryResult.dates, isDescending]);

  const hasFailed = queryResult.failed_keywords?.length > 0;

  return (
    <div style={{ backgroundColor: '#ffffff', borderRadius: '12px', border: '1px solid #e2e8f0', overflow: 'hidden' }}>
      {/* 状态与警告条 */}
      {hasFailed && (
        <div
          style={{
            padding: '12px 20px',
            backgroundColor: '#fff7ed',
            borderBottom: '1px solid #ffedd5',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#c2410c', fontSize: '13px' }}>
            <AlertTriangle size={16} />
            <span>
              注意：<strong>{queryResult.failed_keywords.length}</strong> 个关键词获取失败，对应行指标已标注并禁用全 0 伪造展示。
            </span>
          </div>
          <Button
            size="sm"
            variant="outline"
            loading={isRetrying}
            onClick={() => onRetryFailed(queryResult.failed_keywords)}
          >
            <RefreshCw size={13} /> 仅重试失败关键词
          </Button>
        </div>
      )}

      {/* 头部控制栏 */}
      <div
        style={{
          padding: '16px 20px',
          borderBottom: '1px solid #e2e8f0',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <h3 style={{ fontSize: '15px', fontWeight: 600, color: '#0f172a' }}>
            检索结果 ({queryResult.keywords.length} 关键词，{queryResult.dates.length} 自然日)
          </h3>
          <span style={{ fontSize: '12px', color: '#64748b' }}>
            时间跨度：{queryResult.start_date} ~ {queryResult.end_date}
          </span>
        </div>
        <Button size="sm" variant="ghost" onClick={() => setIsDescending(!isDescending)}>
          <ArrowUpDown size={14} /> {isDescending ? '最新日期在前 (降序)' : '最早日期在前 (升序)'}
        </Button>
      </div>

      {/* 数据表格 */}
      <div style={{ overflowX: 'auto', maxHeight: '600px' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '13px' }}>
          <thead style={{ position: 'sticky', top: 0, backgroundColor: '#f8fafc', zIndex: 10 }}>
            <tr style={{ borderBottom: '1px solid #e2e8f0' }}>
              <th style={{ padding: '10px 14px', minWidth: '150px', fontWeight: 600, color: '#475569' }}>关键词</th>
              <th style={{ padding: '10px 14px', minWidth: '110px', fontWeight: 600, color: '#475569' }}>状态</th>
              {dates.map((d) => (
                <th
                  key={d}
                  colSpan={4}
                  style={{
                    padding: '8px 12px',
                    textAlign: 'center',
                    borderLeft: '1px solid #e2e8f0',
                    fontWeight: 600,
                    color: '#0f172a',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {d}
                </th>
              ))}
            </tr>
            <tr style={{ borderBottom: '1px solid #e2e8f0', backgroundColor: '#f1f5f9', fontSize: '11px', color: '#64748b' }}>
              <th style={{ padding: '6px 14px' }}></th>
              <th style={{ padding: '6px 14px' }}></th>
              {dates.map((d) => (
                <React.Fragment key={d}>
                  <th style={{ padding: '6px 8px', borderLeft: '1px solid #e2e8f0', textAlign: 'right' }}>搜索</th>
                  <th style={{ padding: '6px 8px', textAlign: 'right' }}>曝光</th>
                  <th style={{ padding: '6px 8px', textAlign: 'right' }}>笔记</th>
                  <th style={{ padding: '6px 8px', textAlign: 'right' }}>出价</th>
                </React.Fragment>
              ))}
            </tr>
          </thead>
          <tbody>
            {queryResult.keywords.map((kw) => {
              const statusInfo = queryResult.keyword_statuses[kw] || { status: 'success' };
              const kwStatus = statusInfo.status;
              const kwData = queryResult.data[kw];
              const isFailed = kwStatus !== 'success' && kwStatus !== 'empty';

              return (
                <tr key={kw} style={{ borderBottom: '1px solid #f1f5f9' }}>
                  <td style={{ padding: '12px 14px', fontWeight: 600, color: '#0f172a' }}>{kw}</td>
                  <td style={{ padding: '12px 14px' }}>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
                      <StatusBadge
                        status={kwStatus}
                        label={
                          kwStatus === 'success'
                            ? '成功'
                            : kwStatus === 'empty'
                            ? '暂无数据'
                            : '获取失败'
                        }
                      />
                      {statusInfo.error_message && (
                        <span
                          style={{
                            fontSize: '11px',
                            color: '#dc2626',
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            whiteSpace: 'nowrap',
                            maxWidth: '120px',
                          }}
                          title={statusInfo.error_message}
                        >
                          {statusInfo.error_message}
                        </span>
                      )}
                    </div>
                  </td>
                  {dates.map((d) => {
                    const dayItem = kwData ? kwData[d] : null;
                    return (
                      <React.Fragment key={d}>
                        <td
                          style={{
                            padding: '10px 8px',
                            borderLeft: '1px solid #f1f5f9',
                            textAlign: 'right',
                            color: isFailed ? '#94a3b8' : '#0f172a',
                          }}
                        >
                          {isFailed ? '-' : (dayItem ? dayItem.search_num : 0)}
                        </td>
                        <td
                          style={{
                            padding: '10px 8px',
                            textAlign: 'right',
                            color: isFailed ? '#94a3b8' : '#64748b',
                          }}
                        >
                          {isFailed ? '-' : (dayItem ? dayItem.imp_num : 0)}
                        </td>
                        <td
                          style={{
                            padding: '10px 8px',
                            textAlign: 'right',
                            color: isFailed ? '#94a3b8' : '#64748b',
                          }}
                        >
                          {isFailed ? '-' : (dayItem ? dayItem.note_num : 0)}
                        </td>
                        <td
                          style={{
                            padding: '10px 8px',
                            textAlign: 'right',
                            color: isFailed ? '#94a3b8' : '#64748b',
                          }}
                        >
                          {isFailed
                            ? '-'
                            : dayItem && dayItem.bid
                            ? `¥${Number(dayItem.bid).toFixed(2)}`
                            : '¥0.00'}
                        </td>
                      </React.Fragment>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};

