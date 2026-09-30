import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { History, RefreshCw, ExternalLink, AlertCircle } from 'lucide-react';
import { fetchJson } from '@/shared/api/client';
import { Button } from '@/shared/components/Button';
import { StatusBadge } from '@/shared/components/Badge';
import { Pagination } from '@/shared/components/Pagination';

export const KeywordRunsPage: React.FC = () => {
  const [page, setPage] = useState<number>(1);
  const pageSize = 20;

  const { data, isLoading, refetch } = useQuery<{
    total: number;
    page: number;
    total_pages: number;
    items: any[];
  }>({
    queryKey: ['keywordRuns', page],
    queryFn: () => fetchJson(`/api/keyword/runs?page=${page}&page_size=${pageSize}`),
  });

  const runs = data?.items || [];
  const total = data?.total || 0;
  const totalPages = data?.total_pages || 1;

  return (
    <div style={{ maxWidth: '1240px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '20px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h2 style={{ fontSize: '20px', fontWeight: 700, color: '#0f172a' }}>关键词监控运行记录</h2>
          <p style={{ fontSize: '13px', color: '#64748b', marginTop: '4px' }}>
            追踪关键词每日抓取、全量覆写及追加同步历史，直达飞书表格
          </p>
        </div>
        <Button variant="secondary" size="sm" onClick={() => refetch()}>
          <RefreshCw size={14} /> 刷新日志
        </Button>
      </div>

      <div style={{ backgroundColor: '#ffffff', borderRadius: '12px', border: '1px solid #e2e8f0', overflow: 'hidden' }}>
        {isLoading ? (
          <div style={{ padding: '40px', textAlign: 'center', color: '#94a3b8' }}>加载运行记录中...</div>
        ) : runs.length === 0 ? (
          <div style={{ padding: '60px 20px', textAlign: 'center', color: '#94a3b8' }}>
            <History size={40} style={{ margin: '0 auto 12px', opacity: 0.5 }} />
            <div style={{ fontSize: '15px', color: '#475569', fontWeight: 500 }}>暂无关键词运行记录</div>
          </div>
        ) : (
          <>
            <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '13px' }}>
              <thead>
                <tr style={{ backgroundColor: '#f8fafc', borderBottom: '1px solid #e2e8f0', color: '#475569' }}>
                  <th style={{ padding: '12px 16px', fontWeight: 600 }}>任务名称</th>
                  <th style={{ padding: '12px 16px', fontWeight: 600 }}>触发方式</th>
                  <th style={{ padding: '12px 16px', fontWeight: 600 }}>执行状态</th>
                  <th style={{ padding: '12px 16px', fontWeight: 600 }}>监控词数 / 天数</th>
                  <th style={{ padding: '12px 16px', fontWeight: 600 }}>耗时</th>
                  <th style={{ padding: '12px 16px', fontWeight: 600 }}>完成时间</th>
                  <th style={{ padding: '12px 16px', fontWeight: 600 }}>日志说明</th>
                  <th style={{ padding: '12px 16px', fontWeight: 600, textAlign: 'right' }}>飞书表格</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((r) => (
                  <tr key={r.id} style={{ borderBottom: '1px solid #f1f5f9' }}>
                    <td style={{ padding: '14px 16px', fontWeight: 600, color: '#0f172a' }}>
                      {r.task_name}
                    </td>
                    <td style={{ padding: '14px 16px', color: '#64748b' }}>
                      {r.trigger_type === 'direct_create'
                        ? '直接建表'
                        : r.trigger_type === 'task_init'
                        ? '初始写入'
                        : r.trigger_type === 'scheduled'
                        ? '定时调度'
                        : r.trigger_type === 'append_sync'
                        ? '加词触发'
                        : '手动运行'}
                    </td>
                    <td style={{ padding: '14px 16px' }}>
                      <StatusBadge status={r.status} />
                    </td>
                    <td style={{ padding: '14px 16px' }}>
                      <strong>{r.keywords_count || 0}</strong> 个词 / <strong>{r.days_count || 0}</strong> 天
                    </td>
                    <td style={{ padding: '14px 16px', color: '#64748b' }}>
                      {r.duration_ms ? `${(r.duration_ms / 1000).toFixed(1)}s` : '-'}
                    </td>
                    <td style={{ padding: '14px 16px', color: '#64748b' }}>
                      {r.finished_at ? r.finished_at.substring(0, 16).replace('T', ' ') : '-'}
                    </td>
                    <td style={{ padding: '14px 16px', maxWidth: '300px' }}>
                      {r.error_detail ? (
                        <div style={{ color: '#dc2626', fontSize: '12px', display: 'flex', alignItems: 'center', gap: '4px' }}>
                          <AlertCircle size={14} />
                          <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={r.error_detail}>
                            {r.error_detail}
                          </span>
                        </div>
                      ) : (
                        <span style={{ color: '#475569' }}>{r.message || '更新完成'}</span>
                      )}
                    </td>
                    <td style={{ padding: '14px 16px', textAlign: 'right' }}>
                      {r.spreadsheet_url && (
                        <a
                          href={r.spreadsheet_url}
                          target="_blank"
                          rel="noreferrer"
                          style={{
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '4px',
                            color: '#16a34a',
                            fontWeight: 600,
                            textDecoration: 'none',
                          }}
                        >
                          <ExternalLink size={13} /> 查看表格
                        </a>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <Pagination page={page} totalPages={totalPages} total={total} onPageChange={setPage} />
          </>
        )}
      </div>
    </div>
  );
};

