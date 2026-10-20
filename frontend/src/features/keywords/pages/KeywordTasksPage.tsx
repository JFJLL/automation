import React, { useState } from 'react';
import { Clock } from 'lucide-react';
import { formatRruleText } from '@/shared/utils/formatRrule';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { fetchJson } from '@/shared/api/client';
import { Dialog } from '@/shared/components/Dialog';
import { SchedulePicker } from '@/shared/components/SchedulePicker';
import { KeywordEditor } from '@/shared/components/KeywordEditor';
import { useToast } from '@/shared/components/Toast';
import { TaskStatusBadge } from '@/shared/components/TaskStatusBadge';

export const KeywordTasksPage: React.FC = () => {
  const queryClient = useQueryClient();
  const { showSuccess, showError } = useToast();

  const [editingTask, setEditingTask] = useState<any | null>(null);
  const [editName, setEditName] = useState('');
  const [editRrule, setEditRrule] = useState('');
  const [editKeywords, setEditKeywords] = useState<string[]>([]);
  const [editUpdateMode, setEditUpdateMode] = useState('overwrite');

  const { data: tasks = [], isLoading, refetch } = useQuery<any[]>({
    queryKey: ['keywordTasks'],
    queryFn: () => fetchJson('/api/keyword/tasks'),
  });

  const runNowMutation = useMutation({
    mutationFn: (taskId: number) => fetchJson(`/api/keyword/tasks/${taskId}/run_now`, { method: 'POST' }),
    onSuccess: (res: any) => {
      showSuccess(res.message || '任务同步成功');
      queryClient.invalidateQueries({ queryKey: ['keywordTasks'] });
      queryClient.invalidateQueries({ queryKey: ['keywordRuns'] });
    },
    onError: (err: any) => {
      showError(err.message || '立即同步失败');
    },
  });

  const toggleMutation = useMutation({
    mutationFn: (taskId: number) => fetchJson(`/api/keyword/tasks/${taskId}/toggle`, { method: 'POST' }),
    onSuccess: (res: any) => {
      showSuccess(`任务状态已切换为: ${res.status === 'active' ? '正常运行' : '已暂停'}`);
      queryClient.invalidateQueries({ queryKey: ['keywordTasks'] });
    },
    onError: (err: any) => {
      showError(err.message || '切换状态失败');
    },
  });

  const updateTaskMutation = useMutation({
    mutationFn: (data: { id: number; name: string; rrule: string; keywords: string[]; update_mode: string }) =>
      fetchJson(`/api/keyword/tasks/${data.id}/update`, {
        method: 'POST',
        body: JSON.stringify({
          name: data.name,
          rrule: data.rrule,
          keywords: data.keywords,
          update_mode: data.update_mode,
        }),
      }),
    onSuccess: () => {
      showSuccess('关键词监控任务已更新成功！');
      setEditingTask(null);
      queryClient.invalidateQueries({ queryKey: ['keywordTasks'] });
      queryClient.invalidateQueries({ queryKey: ['keywordRuns'] });
    },
    onError: (err: any) => {
      showError(err.message || '更新任务失败');
    },
  });

  return (
    <div className="card">
      <div className="card-title">
        <span>现有关键词监控任务</span>
        <button type="button" className="btn btn-outline btn-sm" onClick={() => refetch()}>
          🔄 刷新列表
        </button>
      </div>

      <div className="table-container">
        {isLoading ? (
          <div style={{ textAlign: 'center', padding: '30px', color: 'var(--text-muted)' }}>加载任务中...</div>
        ) : tasks.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '30px', color: 'var(--text-muted)' }}>暂无关键词监控任务</div>
        ) : (
          <table style={{ tableLayout: 'fixed', width: '100%', minWidth: '900px' }}>
            <thead>
              <tr>
                <th style={{ width: '14%' }}>任务名称</th>
                <th style={{ width: '15%' }}>关键词详情</th>
                <th style={{ width: '9%' }}>状态</th>
                <th style={{ width: '11%' }}>飞书表格</th>
                <th style={{ width: '8%' }}>模式</th>
                <th style={{ width: '10%' }}>调度频率</th>
                <th style={{ width: '11%' }}>上次执行</th>
                <th style={{ textAlign: 'center', width: '22%' }}>操作</th>
              </tr>
            </thead>
            <tbody>
              {tasks.map((t) => (
                <tr key={t.id} className={t.status !== 'active' ? 'task-row-paused' : ''}>
                  <td style={{ minWidth: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px', minWidth: 0 }}>
                      <strong
                        title={t.name}
                        style={{
                          flex: '1 1 auto',
                          minWidth: 0,
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                        }}
                      >
                        {t.name}
                      </strong>
                      {t.status !== 'active' && (
                        <span
                          className="badge badge-warning"
                          style={{ fontSize: '11px', padding: '1px 6px', flexShrink: 0 }}
                        >
                          已暂停
                        </span>
                      )}
                    </div>
                    <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>ID: #{t.id}</div>
                  </td>
                  <td style={{ maxWidth: '280px' }}>
                    <div style={{ fontWeight: 600, color: 'var(--text-secondary)' }}>
                      有效监控: {t.keywords?.length || 0} 个词
                    </div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px', marginTop: '2px' }}>
                      {t.keywords?.slice(0, 4).map((kw: string) => (
                        <span key={kw} className="badge badge-gray" style={{ fontSize: '11px' }}>
                          {kw}
                        </span>
                      ))}
                      {t.keywords?.length > 4 && (
                        <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>+{t.keywords.length - 4}...</span>
                      )}
                    </div>
                  </td>
                  <td>
                    <span className={`badge ${t.status === 'active' ? 'badge-success' : 'badge-warning'}`} style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                      <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: t.status === 'active' ? 'var(--success)' : 'var(--warning)' }} />
                      <span>{t.status === 'active' ? '正常运行' : '已暂停'}</span>
                    </span>
                  </td>
                  <td>
                    {t.spreadsheet_url ? (
                      <a
                        href={t.spreadsheet_url}
                        target="_blank"
                        rel="noreferrer"
                        style={{ color: 'var(--primary)', fontWeight: 500, textDecoration: 'none' }}
                      >
                        查看飞书表格 ↗
                      </a>
                    ) : '-'}
                  </td>
                  <td>{t.update_mode === 'append' ? '增量追加' : '全量覆写'}</td>
                  <td>
                    <span className="freq-tag" title={t.rrule}>
                      <Clock size={12} className="icon" style={{ opacity: 0.7 }} />
                      <span>{formatRruleText(t.rrule)}</span>
                    </span>
                  </td>
                  <td>
                    <div>{t.last_run_at ? t.last_run_at.substring(0, 16).replace('T', ' ') : '-'}</div>
                    {t.last_status && (
                      <TaskStatusBadge status={t.last_status} error={t.last_error} />
                    )}
                  </td>
                  <td style={{ textAlign: 'center' }}>
                      <div style={{ display: 'inline-flex', gap: '6px', flexWrap: 'nowrap', justifyContent: 'center' }}>
                      <button
                        type="button"
                        className="btn btn-outline btn-sm"
                        disabled={runNowMutation.isPending && runNowMutation.variables === t.id}
                        onClick={() => runNowMutation.mutate(t.id)}
                      >
                        立即同步
                      </button>
                      <button
                        type="button"
                        className={`btn btn-sm ${t.status === 'active' ? 'btn-outline' : 'btn-resume'}`}
                        onClick={() => toggleMutation.mutate(t.id)}
                      >
                        {t.status === 'active' ? '暂停' : '恢复'}
                      </button>
                      <button
                        type="button"
                        className="btn btn-outline btn-sm"
                        onClick={() => {
                          setEditingTask(t);
                          setEditName(t.task_name || t.name);
                          setEditRrule(t.rrule);
                          setEditKeywords([...(t.keywords || [])]);
                          setEditUpdateMode(t.update_mode || 'overwrite');
                        }}
                      >
                        编辑
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* 编辑任务 Dialog */}
      <Dialog
        isOpen={editingTask !== null}
        onClose={() => setEditingTask(null)}
        title="编辑关键词监控任务"
        width="520px"
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div>
            <label style={{ fontSize: '13px', fontWeight: 600, color: '#334155', display: 'block', marginBottom: '6px' }}>
              任务名称
            </label>
            <input
              type="text"
              className="form-control"
              value={editName}
              onChange={(e) => setEditName(e.target.value)}
              style={{ width: '100%' }}
            />
          </div>

          <div>
            <label style={{ fontSize: '13px', fontWeight: 600, color: '#334155', display: 'block', marginBottom: '6px' }}>
              更新方式
            </label>
            <select
              className="form-control"
              value={editUpdateMode}
              onChange={(e) => setEditUpdateMode(e.target.value)}
              style={{ width: '100%', height: '36px', fontSize: '13px' }}
            >
              <option value="overwrite">全量覆写 (覆盖历史窗口数据)</option>
              <option value="append">增量追加 (按日期向右扩展追加)</option>
            </select>
          </div>

          <SchedulePicker
            label="自动化同步周期 (RRULE)"
            value={editRrule}
            onChange={setEditRrule}
          />

          <KeywordEditor
            label="监控关键词管理"
            keywords={editKeywords}
            onChange={setEditKeywords}
          />

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '8px' }}>
            <button type="button" className="btn btn-outline" onClick={() => setEditingTask(null)}>
              取消
            </button>
            <button
              type="button"
              className="btn btn-primary"
              disabled={updateTaskMutation.isPending || !editName.trim() || editKeywords.length === 0}
              onClick={() => {
                if (editingTask) {
                  updateTaskMutation.mutate({
                    id: editingTask.id,
                    name: editName.trim(),
                    rrule: editRrule,
                    keywords: editKeywords,
                    update_mode: editUpdateMode,
                  });
                }
              }}
            >
              {updateTaskMutation.isPending ? '保存中…' : '保存修改'}
            </button>
          </div>
        </div>
      </Dialog>

    </div>
  );
};

