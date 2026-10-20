import React, { useMemo } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  LayoutDashboard,
  Database,
  BarChart3,
  Sparkles,
  Search,
  ShieldCheck,
  Trash2,
  ArchiveRestore,
  Activity,
  ArrowRight,
  CircleAlert,
  ShieldAlert,
} from 'lucide-react';
import { fetchJson } from '@/shared/api/client';

const adminHeaders = () => ({
  'x-admin-token': sessionStorage.getItem('simple_promo_token') || '',
});

interface BoardSummary {
  key: string;
  label: string;
  description: string;
  api: string;
  path: string;
  icon: React.ReactNode;
  accent: string;
}

const BOARDS: BoardSummary[] = [
  {
    key: 'sync',
    label: '数据同步中心',
    description: '飞书表格数据同步任务',
    api: '/api/tasks',
    path: '/tasks',
    icon: <Database size={18} />,
    accent: '#2563eb',
  },
  {
    key: 'keyword',
    label: '聚光关键词',
    description: '关键词指数监控任务',
    api: '/api/keyword/tasks',
    path: '/keyword/tasks',
    icon: <BarChart3 size={18} />,
    accent: '#e11d48',
  },
  {
    key: 'lingxi',
    label: '灵犀关键词',
    description: '灵犀人群覆盖监控任务',
    api: '/api/lingxi/tasks',
    path: '/lingxi/tasks',
    icon: <Sparkles size={18} />,
    accent: '#7c3aed',
  },
];

export const AdminHomePage: React.FC = () => {
  const syncQuery = useQuery<any[]>({
    queryKey: ['adminOverview', 'sync'],
    queryFn: () => fetchJson<any[]>('/api/tasks'),
    staleTime: 60 * 1000,
  });
  const keywordQuery = useQuery<any[]>({
    queryKey: ['adminOverview', 'keyword'],
    queryFn: () => fetchJson<any[]>('/api/keyword/tasks'),
    staleTime: 60 * 1000,
  });
  const lingxiQuery = useQuery<any[]>({
    queryKey: ['adminOverview', 'lingxi'],
    queryFn: () => fetchJson<any[]>('/api/lingxi/tasks'),
    staleTime: 60 * 1000,
  });
  const promoQuery = useQuery<any[]>({
    queryKey: ['adminOverview', 'promo'],
    queryFn: () => fetchJson<any[]>('/api/simple-promo/tasks'),
    staleTime: 60 * 1000,
  });
  const auditQuery = useQuery<any[]>({
    queryKey: ['adminDeletionAudits'],
    queryFn: () =>
      fetchJson<any[]>('/api/admin/deletion-audits', { headers: adminHeaders() }),
    staleTime: 30 * 1000,
  });

  const taskSources = useMemo(
    () => [syncQuery.data, keywordQuery.data, lingxiQuery.data],
    [syncQuery.data, keywordQuery.data, lingxiQuery.data],
  );
  const allTasks = taskSources.flatMap((rows) => rows || []);
  const pausedCount = allTasks.filter((t) => t.status === 'paused').length;
  const activeCount = allTasks.filter((t) => t.status === 'active').length;
  const failedCount = allTasks.filter((t) => t.last_status === 'failed').length;
  const totalCount = allTasks.length;
  const loading = syncQuery.isLoading || keywordQuery.isLoading || lingxiQuery.isLoading;

  return (
    <>
      <div className="page-heading">
        <h2>管理工作台</h2>
        <p>私密管理入口，集中处理任务归档、简单投巡检与操作审计</p>
      </div>

      <div
        className="card"
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))',
          gap: '12px',
          padding: '16px',
        }}
      >
        {[
          { label: '三个板块任务总数', value: totalCount, tone: '#0f172a', icon: <LayoutDashboard size={16} /> },
          { label: '正常运行', value: activeCount, tone: '#059669', icon: <Activity size={16} /> },
          { label: '已暂停', value: pausedCount, tone: '#b45309', icon: <CircleAlert size={16} /> },
          { label: '最近执行失败', value: failedCount, tone: '#dc2626', icon: <CircleAlert size={16} /> },
          { label: '已归档任务快照', value: auditQuery.data?.length ?? 0, tone: '#475569', icon: <ArchiveRestore size={16} /> },
        ].map((item) => (
          <div
            key={item.label}
            style={{
              border: '1px solid var(--border)',
              borderRadius: '10px',
              padding: '14px 16px',
              background: '#fbfcfd',
              minWidth: 0,
            }}
          >
            <div style={{ fontSize: '12px', color: '#64748b', display: 'flex', alignItems: 'center', gap: '6px' }}>
              {item.icon}
              {item.label}
            </div>
            <div style={{ fontSize: '24px', fontWeight: 700, color: item.tone, marginTop: '6px' }}>
              {loading && item.label === '三个板块任务总数' ? '—' : item.value}
            </div>
          </div>
        ))}
      </div>

      <div className="card" style={{ marginTop: '20px' }}>
        <div className="card-title">
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: '8px' }}>
            <ShieldCheck size={16} style={{ color: 'var(--primary)' }} />
            管理功能
          </span>
        </div>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
            gap: '12px',
          }}
        >
          {[
            {
              to: '/admin/tasks',
              icon: <Trash2 size={18} />,
              title: '任务归档删除',
              desc: '只有这里可以删除三个板块的同步任务',
            },
            {
              to: '/admin/audit',
              icon: <ArchiveRestore size={18} />,
              title: '删除归档记录',
              desc: '查看被删除任务的本地快照与运行记录数量',
            },
            {
              to: '/admin/promo',
              icon: <Search size={18} />,
              title: '简单投巡检工作台',
              desc: '巡检老笔记、批量暂停与一键恢复',
            },
          ].map((item) => (
            <Link
              key={item.to}
              to={item.to}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '12px',
                padding: '15px 16px',
                borderRadius: '10px',
                border: '1px solid var(--border)',
                background: '#ffffff',
                color: 'inherit',
                textDecoration: 'none',
              }}
            >
              <span
                style={{
                  width: '36px',
                  height: '36px',
                  borderRadius: '9px',
                  background: 'var(--primary-light)',
                  color: 'var(--primary)',
                  display: 'inline-flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  flexShrink: 0,
                }}
              >
                {item.icon}
              </span>
              <span style={{ minWidth: 0, flex: 1 }}>
                <span style={{ display: 'block', fontSize: '13px', fontWeight: 600, color: '#0f172a' }}>
                  {item.title}
                </span>
                <span style={{ display: 'block', fontSize: '11px', color: '#94a3b8', marginTop: '2px' }}>
                  {item.desc}
                </span>
              </span>
              <ArrowRight size={15} style={{ color: '#cbd5e1', flexShrink: 0 }} />
            </Link>
          ))}
        </div>
      </div>

      <div className="card" style={{ marginTop: '20px' }}>
        <div className="card-title">
          <span>各板块任务概况</span>
          <span className="badge badge-gray">只读概览</span>
        </div>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))',
            gap: '12px',
          }}
        >
          {BOARDS.map((board) => {
            const query = board.key === 'sync' ? syncQuery : board.key === 'keyword' ? keywordQuery : lingxiQuery;
            const rows = query.data || [];
            const paused = rows.filter((t) => t.status === 'paused').length;
            const failed = rows.filter((t) => t.last_status === 'failed').length;
            return (
              <div
                key={board.key}
                style={{
                  border: '1px solid var(--border)',
                  borderRadius: '10px',
                  padding: '15px 16px',
                  background: '#fbfcfd',
                  minWidth: 0,
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: board.accent }}>
                  {board.icon}
                  <strong style={{ fontSize: '13px', color: '#0f172a' }}>{board.label}</strong>
                </div>
                <div style={{ fontSize: '11px', color: '#94a3b8', marginTop: '4px' }}>{board.description}</div>
                <div style={{ display: 'flex', gap: '14px', marginTop: '12px', fontSize: '12px', color: '#475569' }}>
                  <span>共 <strong>{query.isLoading ? '—' : rows.length}</strong> 个</span>
                  <span>暂停 <strong>{paused}</strong></span>
                  <span>失败 <strong style={{ color: failed ? '#dc2626' : undefined }}>{failed}</strong></span>
                </div>
                <Link
                  to={board.path}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '4px',
                    marginTop: '12px',
                    fontSize: '12px',
                    color: 'var(--primary)',
                    textDecoration: 'none',
                  }}
                >
                  查看该板块任务
                  <ArrowRight size={13} />
                </Link>
              </div>
            );
          })}
          <div
            style={{
              border: '1px solid var(--border)',
              borderRadius: '10px',
              padding: '15px 16px',
              background: '#fbfcfd',
              minWidth: 0,
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--primary)' }}>
              <Search size={18} />
              <strong style={{ fontSize: '13px', color: '#0f172a' }}>简单投老笔记</strong>
            </div>
            <div style={{ fontSize: '11px', color: '#94a3b8', marginTop: '4px' }}>定时巡检与批量暂停/恢复</div>
            <div style={{ display: 'flex', gap: '14px', marginTop: '12px', fontSize: '12px', color: '#475569' }}>
              <span>定时任务 <strong>{promoQuery.isLoading ? '—' : promoQuery.data?.length || 0}</strong> 个</span>
            </div>
            <Link
              to="/admin/promo"
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '4px',
                marginTop: '12px',
                fontSize: '12px',
                color: 'var(--primary)',
                textDecoration: 'none',
              }}
            >
              进入巡检工作台
              <ArrowRight size={13} />
            </Link>
          </div>
        </div>
      </div>

      <div
        className="card"
        style={{
          marginTop: '20px',
          display: 'flex',
          alignItems: 'flex-start',
          gap: '10px',
          fontSize: '12px',
          color: '#64748b',
          lineHeight: 1.7,
        }}
      >
        <ShieldAlert size={16} style={{ color: 'var(--warning)', flexShrink: 0, marginTop: '2px' }} />
        <span>
          删除采用归档方式：任务会从原板块列表消失并停止调度，但飞书表格、历史运行记录与本地删除快照都会保留。
          删除快照保存在服务器 <code>sync_console/backups/deletions/</code> 目录。
        </span>
      </div>
    </>
  );
};
