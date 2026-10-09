import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchJson } from '@/shared/api/client';
import { Pagination } from '@/shared/components/Pagination';

export const LingxiRunsPage: React.FC = () => {
  const [page, setPage] = useState<number>(1);
  const pageSize = 20;

  const { data, isLoading, refetch } = useQuery<{
    total: number;
    page: number;
    total_pages: number;
    items: any[];
  }>({
    queryKey: ['lingxiRuns', page],
    queryFn: () => fetchJson(`/api/lingxi/runs?page=${page}&page_size=${pageSize}`),
  });

  const runs = data?.items || [];
  const total = data?.total || 0;
  const totalPages = data?.total_pages || 1;

  return (
    <div className="card">
      <div className="card-title">
        <span>灵犀关键词运行历史记录</span>
        <button type="button" className="btn btn-outline btn-sm" onClick={() => refetch()}>
          🔄 刷新日志
        </button>
      </div>

      <div className="table-container">
        {isLoading ? (
          <div style={{ textAlign: 'center', padding: '30px', color: 'var(--text-muted)' }}>加载日志中...</div>
        ) : runs.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '30px', color: 'var(--text-muted)' }}>暂无灵犀关键词运行记录</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>任务名称</th>
                <th>触发方式</th>
                <th>状态</th>
                <th>关键词数</th>
                <th>耗时</th>
                <th>完成时间</th>
                <th>日志说明</th>
                <th style={{ textAlign: 'right' }}>飞书表格</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr key={r.id}>
                  <td><strong>{r.task_name}</strong></td>
                  <td>
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
                  <td>
                    <span className={`badge ${r.status === 'success' ? 'badge-success' : 'badge-danger'}`}>
                      {r.status === 'success' ? '成功' : '失败'}
                    </span>
                  </td>
                  <td>{r.keywords_count || 0} 个词</td>
                  <td>{r.duration_ms ? `${(r.duration_ms / 1000).toFixed(1)}s` : '-'}</td>
                  <td>{r.finished_at ? r.finished_at.substring(0, 16).replace('T', ' ') : '-'}</td>
                  <td style={{ maxWidth: '360px', whiteSpace: 'normal', wordBreak: 'break-word', lineHeight: 1.4 }}>
                    {r.error_detail ? (
                      <span style={{ color: 'var(--danger)', fontSize: '12px' }} title={r.error_detail}>
                        {r.error_detail}
                      </span>
                    ) : (
                      <span>{r.message || '更新完成'}</span>
                    )}
                  </td>
                  <td style={{ textAlign: 'right' }}>
                    {r.spreadsheet_url && (
                      <a
                        href={r.spreadsheet_url}
                        target="_blank"
                        rel="noreferrer"
                        style={{ color: 'var(--primary)', fontWeight: 500, textDecoration: 'none' }}
                      >
                        查看飞书表格 ↗
                      </a>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <Pagination page={page} totalPages={totalPages} total={total} onPageChange={setPage} />
    </div>
  );
};

