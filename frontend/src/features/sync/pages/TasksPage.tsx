import React, { useState } from 'react';
import { Clock } from 'lucide-react';
import { formatRruleText } from '@/shared/utils/formatRrule';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { fetchJson } from '@/shared/api/client';
import { Dialog } from '@/shared/components/Dialog';
import { SchedulePicker } from '@/shared/components/SchedulePicker';
import { useToast } from '@/shared/components/Toast';
import { TaskStatusBadge } from '@/shared/components/TaskStatusBadge';

export const TasksPage: React.FC = () => {
  const queryClient = useQueryClient();
  const { showSuccess, showError } = useToast();
  const [editingTask, setEditingTask] = useState<any | null>(null);
  const [editName, setEditName] = useState('');
  const [editRrule, setEditRrule] = useState('');
  const [editUpdateMode, setEditUpdateMode] = useState('append');

  const [runningTask, setRunningTask] = useState<any | null>(null);
  const [runMode, setRunMode] = useState<'latest' | 'backfill'>('latest');
  const [backfillStartDate, setBackfillStartDate] = useState<string>('');
  const [backfillEndDate, setBackfillEndDate] = useState<string>('');

  const handleOpenRunDialog = (task: any) => {
    setRunningTask(task);
    setRunMode('latest');
    const yesterday = new Date(Date.now() - 86400000).toISOString().split('T')[0];
    const thirtyDaysAgo = new Date(Date.now() - 30 * 86400000).toISOString().split('T')[0];
    setBackfillEndDate(yesterday);
    setBackfillStartDate(thirtyDaysAgo);
  };

  const updateTaskMutation = useMutation({
    mutationFn: (data: { id: number; name: string; rrule: string; update_mode: string }) =>
      fetchJson(`/api/tasks/${data.id}/update`, {
        method: 'POST',
        body: JSON.stringify({ name: data.name, rrule: data.rrule, update_mode: data.update_mode }),
      }),
    onSuccess: () => {
      showSuccess('任务配置已更新成功！');
      setEditingTask(null);
      queryClient.invalidateQueries({ queryKey: ['syncTasks'] });
    },
    onError: (err: any) => {
      showError(err.message || '更新任务失败');
    },
  });

  const { data: tasks = [], isLoading, refetch } = useQuery<any[]>({
    queryKey: ['syncTasks'],
    queryFn: () => fetchJson('/api/tasks'),
  });

  const runNowMutation = useMutation({
    mutationFn: (params: { taskId: number; mode?: 'latest' | 'backfill'; startDate?: string; endDate?: string }) =>
      fetchJson(`/api/tasks/${params.taskId}/run_now`, {
        method: 'POST',
        body: JSON.stringify({
          mode: params.mode || 'latest',
          start_date: params.startDate,
          end_date: params.endDate,
        }),
      }),
    onSuccess: (res: any) => {
      showSuccess(res.message || '任务同步执行成功');
      setRunningTask(null);
      queryClient.invalidateQueries({ queryKey: ['syncTasks'] });
      queryClient.invalidateQueries({ queryKey: ['syncRuns'] });
    },
    onError: (err: any) => {
      queryClient.invalidateQueries({ queryKey: ['syncTasks'] });
      queryClient.invalidateQueries({ queryKey: ['syncRuns'] });
      showError(err.message || '同步任务执行失败，详情请查看“失败”状态');
    },
  });

  const toggleMutation = useMutation({
    mutationFn: (taskId: number) => fetchJson(`/api/tasks/${taskId}/toggle_status`, { method: 'POST' }),
    onSuccess: (res: any) => {
      showSuccess(`任务状态已切换为: ${res.status === 'active' ? '正常运行' : '已暂停'}`);
      queryClient.invalidateQueries({ queryKey: ['syncTasks'] });
    },
    onError: (err: any) => {
      showError(err.message || '切换状态失败');
    },
  });

  return (
    <div className="card">
      <div className="card-title">
        <span>现有定时同步任务</span>
        <button type="button" className="btn btn-outline btn-sm" onClick={() => refetch()}>
          🔄 刷新列表
        </button>
      </div>

      <div className="table-container">
        {isLoading ? (
          <div style={{ textAlign: 'center', padding: '30px', color: 'var(--text-muted)' }}>加载任务中...</div>
        ) : tasks.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '30px', color: 'var(--text-muted)' }}>暂无同步任务</div>
        ) : (
          <table style={{ tableLayout: 'fixed', width: '100%', minWidth: '900px' }}>
            <thead>
              <tr>
                <th style={{ width: '18%' }}>任务名称</th>
                <th style={{ width: '9%' }}>平台</th>
                <th style={{ width: '10%' }}>状态</th>
                <th style={{ width: '12%' }}>飞书表格</th>
                <th style={{ width: '9%' }}>更新方式</th>
                <th style={{ width: '12%' }}>调度频率</th>
                <th style={{ width: '14%' }}>上次执行</th>
                <th style={{ textAlign: 'center', width: '16%' }}>操作</th>
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
                  <td>
                    <span className="badge badge-gray">
                      {t.platform === 'jzt' ? '京准通' : t.platform === 'taobao' ? '淘宝星河' : '小红书聚光'}
                      {t.sub_account_name ? ` (${t.sub_account_name})` : ''}
                    </span>
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
                        style={{ color: t.status === 'active' ? 'var(--primary)' : 'var(--text-muted)', fontWeight: 500, textDecoration: 'none' }}
                      >
                        查看飞书表格 ↗
                      </a>
                    ) : '-'}
                  </td>
                  <td>{t.update_mode === 'overwrite' ? '全量覆写' : '增量更新'}</td>
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
                    <div style={{ display: 'inline-flex', gap: '6px', flexWrap: 'wrap', justifyContent: 'center' }}>
                      <button
                        type="button"
                        className="btn btn-outline btn-sm"
                        disabled={runNowMutation.isPending && (runNowMutation.variables as any)?.taskId === t.id}
                        onClick={() => handleOpenRunDialog(t)}
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
                          setEditName(t.name);
                          setEditRrule(t.rrule);
                          setEditUpdateMode(t.update_mode || 'append');
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
        title="编辑同步任务"
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
              <option value="append">增量更新 (自动校准并防重)</option>
              <option value="overwrite">全量覆写 (覆盖同步历史窗口)</option>
            </select>
          </div>

          <SchedulePicker
            label="自动化同步周期 (RRULE)"
            value={editRrule}
            onChange={setEditRrule}
          />

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '8px' }}>
            <button type="button" className="btn btn-outline" onClick={() => setEditingTask(null)}>
              取消
            </button>
            <button
              type="button"
              className="btn btn-primary"
              disabled={updateTaskMutation.isPending || !editName.trim()}
              onClick={() => {
                if (editingTask) {
                  updateTaskMutation.mutate({
                    id: editingTask.id,
                    name: editName.trim(),
                    rrule: editRrule,
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

      {/* 立即同步与补充历史数据 Dialog */}
      <Dialog
        isOpen={runningTask !== null}
        onClose={() => setRunningTask(null)}
        title={`执行数据同步 - ${runningTask?.name || ''}`}
        width="540px"
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div style={{ fontSize: '13px', color: '#475569', lineHeight: '1.5' }}>
            请选择本次数据同步的执行模式：
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            {/* 模式 1：同步最新数据（默认） */}
            <label
              style={{
                display: 'flex',
                alignItems: 'flex-start',
                gap: '12px',
                padding: '12px 14px',
                borderRadius: '8px',
                border: `1.5px solid ${runMode === 'latest' ? '#f53f3f' : '#e2e8f0'}`,
                background: runMode === 'latest' ? '#fff5f5' : '#ffffff',
                cursor: 'pointer',
                transition: 'all 0.15s ease'
              }}
            >
              <input
                type="radio"
                name="runMode"
                value="latest"
                checked={runMode === 'latest'}
                onChange={() => setRunMode('latest')}
                style={{ marginTop: '3px', accentColor: '#f53f3f', cursor: 'pointer' }}
              />
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: 600, fontSize: '13px', color: '#1e293b' }}>
                  ⚡ 同步最新数据（默认）
                </div>
                <div style={{ fontSize: '12px', color: '#64748b', marginTop: '3px', lineHeight: '1.4' }}>
                  按任务原定规则，增量抓取最新数据并校准防重（最近 {runningTask?.calibration_days ?? 2} 天）。
                </div>
              </div>
            </label>

            {/* 模式 2：补充历史数据 */}
            <label
              style={{
                display: 'flex',
                alignItems: 'flex-start',
                gap: '12px',
                padding: '12px 14px',
                borderRadius: '8px',
                border: `1.5px solid ${runMode === 'backfill' ? '#f53f3f' : '#e2e8f0'}`,
                background: runMode === 'backfill' ? '#fff5f5' : '#ffffff',
                cursor: 'pointer',
                transition: 'all 0.15s ease'
              }}
            >
              <input
                type="radio"
                name="runMode"
                value="backfill"
                checked={runMode === 'backfill'}
                onChange={() => setRunMode('backfill')}
                style={{ marginTop: '3px', accentColor: '#f53f3f', cursor: 'pointer' }}
              />
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: 600, fontSize: '13px', color: '#1e293b' }}>
                  📅 补充历史数据
                </div>
                <div style={{ fontSize: '12px', color: '#64748b', marginTop: '3px', lineHeight: '1.4' }}>
                  选择开始和结束日期，获取该区间全量数据合入现有表格；相同记录原地更新，已有历史完好保留，不影响日常定时更新规则。
                </div>
              </div>
            </label>
          </div>

          {/* 当选择补充历史数据时，展开日期选择器 */}
          {runMode === 'backfill' && (
            <div style={{
              background: '#f8fafc',
              border: '1px solid #e2e8f0',
              borderRadius: '8px',
              padding: '14px',
              display: 'flex',
              flexDirection: 'column',
              gap: '12px',
              animation: 'uiFadeUp .2s both'
            }}>
              <div style={{ fontSize: '12px', fontWeight: 600, color: '#334155' }}>
                选择需要补充的历史区间：
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                <div>
                  <label style={{ fontSize: '12px', color: '#64748b', display: 'block', marginBottom: '4px' }}>
                    开始日期
                  </label>
                  <input
                    type="date"
                    className="form-control"
                    value={backfillStartDate}
                    onChange={(e) => setBackfillStartDate(e.target.value)}
                    style={{ width: '100%', height: '36px', fontSize: '13px' }}
                  />
                </div>
                <div>
                  <label style={{ fontSize: '12px', color: '#64748b', display: 'block', marginBottom: '4px' }}>
                    结束日期
                  </label>
                  <input
                    type="date"
                    className="form-control"
                    value={backfillEndDate}
                    onChange={(e) => setBackfillEndDate(e.target.value)}
                    style={{ width: '100%', height: '36px', fontSize: '13px' }}
                  />
                </div>
              </div>

              {/* 快捷范围预设 */}
              <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', alignItems: 'center' }}>
                <span style={{ fontSize: '11px', color: '#94a3b8' }}>快捷范围:</span>
                {[
                  { label: '近30天', days: 30 },
                  { label: '近60天', days: 60 },
                  { label: '近90天', days: 90 },
                  { label: '今年迄今 (1月1日)', startYear: true },
                ].map((preset, idx) => (
                  <button
                    key={idx}
                    type="button"
                    className="btn btn-outline btn-sm"
                    style={{ fontSize: '11px', height: '24px', padding: '0 8px' }}
                    onClick={() => {
                      const end = new Date(Date.now() - 86400000).toISOString().split('T')[0];
                      let start = '';
                      if (preset.startYear) {
                        start = `${new Date().getFullYear()}-01-01`;
                      } else {
                        start = new Date(Date.now() - (preset.days || 30) * 86400000).toISOString().split('T')[0];
                      }
                      setBackfillStartDate(start);
                      setBackfillEndDate(end);
                    }}
                  >
                    {preset.label}
                  </button>
                ))}
              </div>
            </div>
          )}

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '8px' }}>
            <button
              type="button"
              className="btn btn-outline"
              onClick={() => setRunningTask(null)}
              disabled={runNowMutation.isPending}
            >
              取消
            </button>
            <button
              type="button"
              className="btn btn-primary"
              disabled={runNowMutation.isPending || (runMode === 'backfill' && (!backfillStartDate || !backfillEndDate))}
              onClick={() => {
                if (runningTask) {
                  runNowMutation.mutate({
                    taskId: runningTask.id,
                    mode: runMode,
                    startDate: runMode === 'backfill' ? backfillStartDate : undefined,
                    endDate: runMode === 'backfill' ? backfillEndDate : undefined,
                  });
                }
              }}
            >
              {runNowMutation.isPending ? '正在执行同步中…' : '确认执行'}
            </button>
          </div>
        </div>
      </Dialog>
    </div>
  );
};

