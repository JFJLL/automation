import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { History, RefreshCw, AlertCircle } from 'lucide-react';
import { fetchJson } from '@/shared/api/client';
import { Button } from '@/shared/components/Button';
import { StatusBadge } from '@/shared/components/Badge';
import { Pagination } from '@/shared/components/Pagination';

export const RunsPage: React.FC = () => {
  const [page, setPage] = useState<number>(1);
  const pageSize = 20;

  const { data, isLoading, refetch } = useQuery<{
    total: number;
    page: number;
    total_pages: number;
    items: any[];
  }>({
    queryKey: ['syncRuns', page],
    queryFn: () => fetchJson(`/api/runs?page=${page}&page_size=${pageSize}`),
  });

  const runs = data?.items || [];
  const total = data?.total || 0;
  const totalPages = data?.total_pages || 1;

  return (
    <div style={{ maxWidth: '1200px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '20px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h2 style={{ fontSize: '20px', fontWeight: 700, color: '#0f172a' }}>主数据同步运行记录</h2>
          <p style={{ fontSize: '13px', color: '#64748b', marginTop: '4px' }}>
            查看计划调度与手动触发的历史运行执行状态与耗时日志
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
            <div style={{ fontSize: '15px', color: '#475569', fontWeight: 500 }}>暂无运行记录</div>
          </div>
        ) : (
          <>
            <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '13px' }}>
              <thead>
                <tr style={{ backgroundColor: '#f8fafc', borderBottom: '1px solid #e2e8f0', color: '#475569' }}>
                  <th style={{ padding: '12px 16px', fontWeight: 600 }}>任务名称</th>
                  <th style={{ padding: '12px 16px', fontWeight: 600 }}>平台</th>
                  <th style={{ padding: '12px 16px', fontWeight: 600 }}>触发方式</th>
                  <th style={{ padding: '12px 16px', fontWeight: 600 }}>执行状态</th>
                  <th style={{ padding: '12px 16px', fontWeight: 600 }}>拉取 / 追加 / 覆写</th>
                  <th style={{ padding: '12px 16px', fontWeight: 600 }}>耗时</th>
                  <th style={{ padding: '12px 16px', fontWeight: 600 }}>执行时间</th>
                  <th style={{ padding: '12px 16px', fontWeight: 600 }}>日志信息</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((r) => (
                  <tr key={r.id} style={{ borderBottom: '1px solid #f1f5f9' }}>
                    <td style={{ padding: '14px 16px', fontWeight: 600, color: '#0f172a' }}>
                      {r.task_name || `任务 #${r.task_id}`}
                    </td>
                    <td style={{ padding: '14px 16px', color: '#475569' }}>
                      {r.platform === 'jzt' ? '京准通' : r.platform === 'taobao' ? '淘宝星河' : '小红书聚光'}
                    </td>
                    <td style={{ padding: '14px 16px', color: '#64748b' }}>
                      {r.trigger_type === 'scheduled' ? '定时调度' : r.trigger_type === 'manual' ? '手动执行' : r.trigger_type}
                    </td>
                    <td style={{ padding: '14px 16px' }}>
                      <StatusBadge status={r.status} />
                    </td>
                    <td style={{ padding: '14px 16px' }}>
                      <span style={{ color: '#0f172a' }}>{r.rows_fetched || 0}</span> /{' '}
                      <span style={{ color: '#16a34a' }}>+{r.rows_appended || 0}</span> /{' '}
                      <span style={{ color: '#0284c7' }}>{r.rows_updated || 0}</span>
                    </td>
                    <td style={{ padding: '14px 16px', color: '#64748b' }}>
                      {r.duration_ms ? `${(r.duration_ms / 1000).toFixed(1)}s` : '-'}
                    </td>
                    <td style={{ padding: '14px 16px', color: '#64748b' }}>
                      {r.started_at ? r.started_at.substring(0, 16).replace('T', ' ') : '-'}
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
                        <span style={{ color: '#475569' }}>{r.message || '执行成功'}</span>
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

