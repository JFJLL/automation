import React, { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ArchiveRestore, ArrowLeft, RefreshCw } from 'lucide-react';
import { fetchJson } from '@/shared/api/client';

const adminHeaders = () => ({
  'x-admin-token': sessionStorage.getItem('simple_promo_token') || '',
});

const MODULE_LABELS: Record<string, string> = {
  sync: '数据同步中心',
  keyword: '聚光关键词',
  lingxi: '灵犀关键词',
};

export const AdminAuditPage: React.FC = () => {
  const [keyword, setKeyword] = useState('');
  const { data = [], isLoading, isFetching, refetch } = useQuery<any[]>({
    queryKey: ['adminDeletionAudits'],
    queryFn: () =>
      fetchJson<any[]>('/api/admin/deletion-audits', { headers: adminHeaders() }),
    staleTime: 30 * 1000,
  });

  const filtered = useMemo(() => {
    const kw = keyword.trim().toLowerCase();
    if (!kw) return data;
    return data.filter((row) => {
      const haystack = `${row.task_name || ''} ${row.task_id || ''} ${row.module || ''}`.toLowerCase();
      return haystack.includes(kw);
    });
  }, [data, keyword]);

  return (
    <>
      <div className="page-heading">
        <h2>删除归档记录</h2>
        <p>每次在管理后台归档删除任务，都会在服务器 backups/deletions 下保留完整快照</p>
      </div>

      <div className="card">
        <div className="card-title" style={{ flexWrap: 'wrap', gap: '12px' }}>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: '8px' }}>
            <ArchiveRestore size={16} style={{ color: 'var(--primary)' }} />
            已归档任务
            <span className="badge badge-gray">{data.length} 条</span>
          </span>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: '8px' }}>
            <input
              className="form-control"
              placeholder="搜索任务名称、ID 或板块"
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
              style={{ width: '220px', height: '32px', fontSize: '12px' }}
            />
            <button
              type="button"
              className="btn btn-outline btn-sm"
              onClick={() => refetch()}
              disabled={isFetching}
            >
              <RefreshCw size={13} style={{ marginRight: '4px' }} />
              {isFetching ? '刷新中…' : '刷新'}
            </button>
            <Link to="/admin/tasks" className="btn btn-outline btn-sm" style={{ textDecoration: 'none' }}>
              <ArrowLeft size={13} style={{ marginRight: '4px' }} />
              返回任务管理
            </Link>
          </span>
        </div>

        {isLoading ? (
          <div className="empty-prompt">正在加载归档记录…</div>
        ) : filtered.length === 0 ? (
          <div className="empty-prompt">
            {keyword.trim() ? '没有匹配的归档记录' : '暂无归档记录，删除任务后会在这里留下快照'}
          </div>
        ) : (
          <div className="table-container">
            <table style={{ tableLayout: 'fixed', width: '100%', minWidth: '820px' }}>
              <thead>
                <tr>
                  <th style={{ width: '15%' }}>板块</th>
                  <th style={{ width: '8%' }}>任务ID</th>
                  <th>任务名称</th>
                  <th style={{ width: '16%' }}>删除时间</th>
                  <th style={{ width: '16%' }}>保留记录</th>
                  <th style={{ width: '12%' }}>快照文件</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((row) => (
                  <tr key={row.filename}>
                    <td>
                      <span className="badge badge-gray">{MODULE_LABELS[row.module] || row.module || '-'}</span>
                    </td>
                    <td style={{ color: '#94a3b8', fontSize: '12px' }}>#{row.task_id}</td>
                    <td>
                      <div
                        title={row.task_name || ''}
                        style={{ fontWeight: 600, fontSize: '13px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                      >
                        {row.task_name || '(未命名任务)'}
                      </div>
                    </td>
                    <td style={{ fontSize: '12px', color: '#64748b', whiteSpace: 'nowrap' }}>
                      {row.deleted_at ? String(row.deleted_at).replace('T', ' ').slice(0, 19) : '-'}
                    </td>
                    <td style={{ fontSize: '12px', color: '#475569' }}>
                      {Object.entries(row.related_counts || {})
                        .map(([key, value]) => `${key === 'runs' ? '运行记录' : key === 'task_sheets' ? '子表配置' : key} ${value}`)
                        .join(' / ') || '-'}
                    </td>
                    <td
                      title={row.filename}
                      style={{ fontSize: '11px', color: '#94a3b8', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                    >
                      {row.filename}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
};
