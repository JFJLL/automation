import React, { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Database,
  BarChart3,
  Sparkles,
  ShieldCheck,
  Trash2,
  RefreshCw,
  AlertTriangle,
  ExternalLink,
} from 'lucide-react';
import { fetchJson } from '@/shared/api/client';
import { Dialog } from '@/shared/components/Dialog';
import { useToast } from '@/shared/components/Toast';
import { formatRruleText } from '@/shared/utils/formatRrule';

type Section = 'sync' | 'keyword' | 'lingxi';

interface TaskMeta {
  key: Section;
  label: string;
  icon: React.ReactNode;
  api: string;
  listPath: string;
  deleteApi: (id: number) => string;
  nameField: 'name' | 'task_name';
  color: string;
}

const SECTIONS: TaskMeta[] = [
  {
    key: 'sync',
    label: '数据同步中心',
    icon: <Database size={15} />,
    api: '/api/tasks',
    listPath: '/tasks',
    deleteApi: (id) => `/api/tasks/${id}`,
    nameField: 'name',
    color: '#165dff',
  },
  {
    key: 'keyword',
    label: '聚光关键词',
    icon: <BarChart3 size={15} />,
    api: '/api/keyword/tasks',
    listPath: '/keyword/tasks',
    deleteApi: (id) => `/api/keyword/tasks/${id}`,
    nameField: 'name',
    color: '#ea3445',
  },
  {
    key: 'lingxi',
    label: '灵犀关键词',
    icon: <Sparkles size={15} />,
    api: '/api/lingxi/tasks',
    listPath: '/lingxi/tasks',
    deleteApi: (id) => `/api/lingxi/tasks/${id}`,
    nameField: 'name',
    color: '#7c3aed',
  },
];

const TABS: Array<{ key: Section; label: string }> = [
  { key: 'sync', label: '数据同步中心' },
  { key: 'keyword', label: '聚光关键词' },
  { key: 'lingxi', label: '灵犀关键词' },
];

export const AdminTasksPage: React.FC = () => {
  const queryClient = useQueryClient();
  const { showSuccess, showError } = useToast();
  const [activeTab, setActiveTab] = useState<Section>('sync');
  const [pendingDelete, setPendingDelete] = useState<{ meta: TaskMeta; task: any } | null>(null);
  const [keyword, setKeyword] = useState('');

  const activeMeta = useMemo(
    () => SECTIONS.find((s) => s.key === activeTab) || SECTIONS[0],
    [activeTab],
  );

  const { data: tasks = [], isLoading, isFetching, refetch } = useQuery<any[]>({
    queryKey: ['adminTasks', activeMeta.key],
    queryFn: () => fetchJson<any[]>(activeMeta.api),
    staleTime: 30 * 1000,
  });

  const deleteMutation = useMutation({
    mutationFn: async ({ meta, task }: { meta: TaskMeta; task: any }) =>
      fetchJson(meta.deleteApi(task.id), {
        method: 'DELETE',
        headers: {
          'x-admin-token': sessionStorage.getItem('simple_promo_token') || '',
        },
      }),
    onSuccess: (_res, vars) => {
      showSuccess(`已归档删除「${vars.task[vars.meta.nameField] || vars.task.id}」`);
      setPendingDelete(null);
      queryClient.invalidateQueries({ queryKey: ['adminTasks'] });
      queryClient.invalidateQueries({ queryKey: ['adminOverview'] });
      queryClient.invalidateQueries({ queryKey: ['adminDeletionAudits'] });
      queryClient.invalidateQueries({ queryKey: ['syncTasks'] });
      queryClient.invalidateQueries({ queryKey: ['keywordTasks'] });
      queryClient.invalidateQueries({ queryKey: ['lingxiTasks'] });
    },
    onError: (err: any) => {
      showError(err.message || '删除失败');
    },
  });

  const filtered = useMemo(() => {
    const kw = keyword.trim().toLowerCase();
    if (!kw) return tasks;
    return tasks.filter((t) => {
      const name = String(t[activeMeta.nameField] || '').toLowerCase();
      return name.includes(kw) || String(t.id).includes(kw);
    });
  }, [tasks, keyword, activeMeta]);

  return (
    <>
      <div className="page-heading">
        <h2>任务归档删除</h2>
        <p>三个板块的删除入口只在这里开放，删除后任务停止调度，运行记录与本地快照保留</p>
      </div>

      {/* 任务清理 */}
      <div className="card">
        <div className="card-title" style={{ flexWrap: 'wrap', gap: '12px' }}>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: '8px' }}>
            <ShieldCheck size={16} style={{ color: 'var(--primary)' }} />
            选择板块并归档任务
            <span className="badge badge-gray">管理员专属</span>
          </span>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: '8px' }}>
            <input
              className="form-control"
              placeholder="搜索任务名称或 ID"
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
          </span>
        </div>

        <div className="nav-tabs" style={{ marginBottom: '14px', width: 'fit-content' }}>
          {TABS.map((tab) => (
            <button
              key={tab.key}
              type="button"
              className={`nav-tab ${activeTab === tab.key ? 'active' : ''}`}
              onClick={() => setActiveTab(tab.key as Section)}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {isLoading ? (
          <div className="empty-prompt">正在加载任务列表…</div>
        ) : filtered.length === 0 ? (
          <div className="empty-prompt">
            {keyword.trim() ? '没有匹配的任务' : '该板块暂无任务'}
          </div>
        ) : (
          <div className="table-container">
            <table style={{ tableLayout: 'fixed', width: '100%', minWidth: '760px' }}>
              <thead>
                <tr>
                  <th style={{ width: '70px' }}>ID</th>
                  <th>任务名称</th>
                  <th style={{ width: '110px' }}>状态</th>
                  <th style={{ width: '170px' }}>执行周期</th>
                  <th style={{ width: '140px' }}>下次运行</th>
                  <th style={{ width: '118px' }}>操作</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((t) => (
                  <tr key={`${activeMeta.key}-${t.id}`}>
                    <td style={{ color: '#94a3b8', fontSize: '12px' }}>#{t.id}</td>
                    <td>
                      <div
                        style={{
                          fontWeight: 600,
                          fontSize: '13px',
                          color: '#0f172a',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                        }}
                        title={t[activeMeta.nameField] || ''}
                      >
                        {t[activeMeta.nameField] || '(未命名任务)'}
                      </div>
                      {t.platform ? (
                        <div
                          style={{
                            fontSize: '11px',
                            color: '#94a3b8',
                            marginTop: '2px',
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            whiteSpace: 'nowrap',
                          }}
                        >
                          {t.platform === 'jzt' ? '京准通' : t.platform === 'taobao' ? '淘宝星河' : '小红书聚光'}
                          {t.sheets ? ` · ${t.sheets.length} 个子表` : ''}
                          {t.keywords ? ` · ${t.keywords.length} 个关键词` : ''}
                        </div>
                      ) : null}
                    </td>
                    <td>
                      <span className={`badge ${t.status === 'active' ? 'badge-success' : 'badge-gray'}`}>
                        {t.status === 'active' ? '运行中' : t.status === 'paused' ? '已暂停' : t.status || '-'}
                      </span>
                    </td>
                    <td style={{ fontSize: '12px', color: '#475569', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {t.rrule ? formatRruleText(t.rrule) : '-'}
                    </td>
                    <td style={{ fontSize: '12px', color: '#64748b', whiteSpace: 'nowrap' }}>
                      {t.next_run_at ? String(t.next_run_at).replace('T', ' ').slice(0, 16) : '-'}
                    </td>
                    <td>
                      <div style={{ display: 'inline-flex', gap: '6px' }}>
                        <Link
                          to={activeMeta.listPath}
                          className="btn btn-outline btn-sm"
                          style={{ textDecoration: 'none' }}
                          title="跳转到该板块任务列表"
                        >
                          <ExternalLink size={13} />
                        </Link>
                        <button
                          type="button"
                          className="btn btn-danger btn-sm"
                          disabled={deleteMutation.isPending}
                          onClick={() => setPendingDelete({ meta: activeMeta, task: t })}
                        >
                          <Trash2 size={13} style={{ marginRight: '4px' }} />
                          归档删除
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <Dialog
        isOpen={pendingDelete !== null}
        onClose={() => setPendingDelete(null)}
        title={`确认归档删除${pendingDelete ? pendingDelete.meta.label : ''}任务`}
        width="440px"
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
          <div
            style={{
              display: 'flex',
              gap: '10px',
              padding: '12px 14px',
              background: '#fff7ed',
              border: '1px solid #fed7aa',
              borderRadius: '8px',
              fontSize: '12px',
              color: '#9a3412',
              lineHeight: 1.6,
            }}
          >
            <AlertTriangle size={16} style={{ flexShrink: 0, marginTop: '2px' }} />
            <span>
              该任务会从列表移除并立即停止调度；飞书表格、历史运行记录与本地删除快照都会保留，
              可在管理后台“删除归档记录”里回溯。此操作不可撤销。
            </span>
          </div>
          <div style={{ fontSize: '13px', color: '#334155' }}>
            任务：
            <strong>
              {pendingDelete ? pendingDelete.task[pendingDelete.meta.nameField] : ''}
            </strong>
            {pendingDelete ? (
              <span style={{ color: '#94a3b8', marginLeft: '6px' }}>#{pendingDelete.task.id}</span>
            ) : null}
          </div>
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
            <button type="button" className="btn btn-outline" onClick={() => setPendingDelete(null)}>
              取消
            </button>
            <button
              type="button"
              className="btn btn-danger"
              disabled={deleteMutation.isPending}
              onClick={() => pendingDelete && deleteMutation.mutate(pendingDelete)}
            >
              {deleteMutation.isPending ? '归档中…' : '确认归档删除'}
            </button>
          </div>
        </div>
      </Dialog>
    </>
  );
};
