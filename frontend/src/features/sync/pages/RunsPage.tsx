import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchJson } from '@/shared/api/client';
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
    <div className="card">
      <div className="card-title">
        <span>历史运行记录与状态</span>
        <button type="button" className="btn btn-outline btn-sm" onClick={() => refetch()}>
          🔄 刷新日志
        </button>
      </div>

      <div className="table-container">
        {isLoading ? (
          <div style={{ textAlign: 'center', padding: '30px', color: 'var(--text-muted)' }}>加载日志中...</div>
        ) : runs.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '30px', color: 'var(--text-muted)' }}>暂无运行记录</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>运行ID</th>
                <th>任务名称</th>
                <th>触发方式</th>
                <th>开始时间</th>
                <th>结束时间</th>
                <th>状态</th>
                <th>数据结果</th>
                <th>错误详情</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr key={r.id}>
                  <td>#{r.id}</td>
                  <td><strong>{r.task_name || `任务 #${r.task_id}`}</strong></td>
                  <td>{r.trigger_type === 'scheduled' ? '定时调度' : '手动运行'}</td>
                  <td>{r.started_at ? r.started_at.substring(0, 16).replace('T', ' ') : '-'}</td>
                  <td>{r.finished_at ? r.finished_at.substring(0, 16).replace('T', ' ') : '-'}</td>
                  <td>
                    <span className={`badge ${r.status === 'success' ? 'badge-success' : r.status === 'running' ? 'badge-primary' : 'badge-danger'}`}>
                      {r.status === 'success' ? '成功' : r.status === 'running' ? '运行中' : '失败'}
                    </span>
                  </td>
                  <td>
                    拉取 {r.rows_fetched || 0} 行 / 追加 {r.rows_appended || 0} 行 / 覆写 {r.rows_updated || 0} 行
                  </td>
                  <td style={{ maxWidth: '300px' }}>
                    {r.error_detail ? (
                      <span style={{ color: 'var(--danger)', fontSize: '12px' }} title={r.error_detail}>
                        {r.error_detail}
                      </span>
                    ) : (
                      <span style={{ color: 'var(--text-muted)' }}>-</span>
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

