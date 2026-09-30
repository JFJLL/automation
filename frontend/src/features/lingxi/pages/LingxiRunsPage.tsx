import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { History, ExternalLink, CheckCircle2, XCircle, Clock } from 'lucide-react';
import { fetchJson } from '@/shared/api/client';

export const LingxiRunsPage: React.FC = () => {
  const { data: runs = [], isLoading } = useQuery<any[]>({
    queryKey: ['lingxiRuns'],
    queryFn: () => fetchJson('/api/lingxi/runs'),
    refetchInterval: 5000,
  });

  return (
    <div className="tab-pane active" style={{ padding: '0 4px' }}>
      <div className="section-head" style={{ marginBottom: '16px' }}>
        <div className="section-title">
          <div className="title-icon" style={{ background: '#fef2f2', color: '#ef4444' }}>
            <History size={20} />
          </div>
          <div>
            <h2>灵犀关键词运行记录</h2>
            <div className="section-desc">查看小红书灵犀关键词监控任务与即时同步的历史执行日志及飞书报表状态。</div>
          </div>
        </div>
      </div>

      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        <div style={{ overflowX: 'auto' }}>
          <table className="table" style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
            <thead>
              <tr style={{ background: '#f8fafc', borderBottom: '1px solid #e2e8f0' }}>
                <th style={{ padding: '12px 16px', fontSize: '13px', color: '#475569' }}>任务名称</th>
                <th style={{ padding: '12px 16px', fontSize: '13px', color: '#475569' }}>触发方式</th>
                <th style={{ padding: '12px 16px', fontSize: '13px', color: '#475569' }}>开始时间</th>
                <th style={{ padding: '12px 16px', fontSize: '13px', color: '#475569' }}>耗时</th>
                <th style={{ padding: '12px 16px', fontSize: '13px', color: '#475569' }}>关键词词数</th>
                <th style={{ padding: '12px 16px', fontSize: '13px', color: '#475569' }}>飞书表格</th>
                <th style={{ padding: '12px 16px', fontSize: '13px', color: '#475569' }}>状态</th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                <tr>
                  <td colSpan={7} style={{ padding: '30px', textAlign: 'center', color: '#94a3b8' }}>
                    加载运行记录中...
                  </td>
                </tr>
              ) : runs.length === 0 ? (
                <tr>
                  <td colSpan={7} style={{ padding: '40px', textAlign: 'center', color: '#94a3b8' }}>
                    暂无运行记录
                  </td>
                </tr>
              ) : (
                runs.map((run) => {
                  const isSuccess = run.status === 'success';
                  const isRunning = run.status === 'running';

                  return (
                    <tr key={run.id} style={{ borderBottom: '1px solid #f1f5f9' }}>
                      <td style={{ padding: '12px 16px', fontWeight: 600, color: '#1e293b' }}>
                        {run.task_name}
                      </td>
                      <td style={{ padding: '12px 16px', fontSize: '13px', color: '#64748b' }}>
                        {run.trigger_type === 'scheduled' ? '定时触发' : '手动执行'}
                      </td>
                      <td style={{ padding: '12px 16px', fontSize: '13px', color: '#475569' }}>
                        {run.started_at ? new Date(run.started_at).toLocaleString() : '-'}
                      </td>
                      <td style={{ padding: '12px 16px', fontSize: '13px', color: '#475569' }}>
                        {run.duration_ms ? `${(run.duration_ms / 1000).toFixed(1)}s` : '-'}
                      </td>
                      <td style={{ padding: '12px 16px', fontSize: '13px', color: '#475569' }}>
                        {run.keywords_count} 个词
                      </td>
                      <td style={{ padding: '12px 16px' }}>
                        {run.spreadsheet_url ? (
                          <a
                            href={run.spreadsheet_url}
                            target="_blank"
                            rel="noreferrer"
                            style={{ color: '#0284c7', display: 'inline-flex', alignItems: 'center', gap: '4px', textDecoration: 'none' }}
                          >
                            <span>打开表格</span>
                            <ExternalLink size={13} />
                          </a>
                        ) : (
                          <span style={{ color: '#94a3b8' }}>-</span>
                        )}
                      </td>
                      <td style={{ padding: '12px 16px' }}>
                        {isRunning ? (
                          <span className="badge badge-gray" style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                            <Clock size={12} className="animate-spin" />
                            运行中
                          </span>
                        ) : isSuccess ? (
                          <span className="badge badge-success" style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                            <CheckCircle2 size={12} />
                            成功
                          </span>
                        ) : (
                          <span
                            className="badge badge-danger"
                            title={run.error_detail || run.message}
                            style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', cursor: 'pointer' }}
                          >
                            <XCircle size={12} />
                            失败
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

