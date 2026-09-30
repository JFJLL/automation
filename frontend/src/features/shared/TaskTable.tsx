import React, { useState } from 'react';
import { Clock } from 'lucide-react';
import { formatRruleText } from '@/shared/utils/formatRrule';
import { Dialog } from '@/shared/components/Dialog';
import { useTaskMutations } from './useTaskMutations';

export interface TaskTableProps {
  tasks: any[];
  isLoading: boolean;
  refetch: () => void;
  mutations: ReturnType<typeof useTaskMutations>;
  title?: string;
  emptyText?: string;
}

export const TaskTable: React.FC<TaskTableProps> = ({
  tasks = [],
  isLoading,
  refetch,
  mutations,
  title = '现有任务列表',
  emptyText = '暂无任务',
}) => {
  const [appendModalTaskId, setAppendModalTaskId] = useState<number | null>(null);
  const [appendWordsInput, setAppendWordsInput] = useState('');
  const [removeModalTaskId, setRemoveModalTaskId] = useState<number | null>(null);
  const [removeWordSelect, setRemoveWordSelect] = useState<string[]>([]);
  const [deleteConfirmId, setDeleteConfirmId] = useState<number | null>(null);
  const [pauseConfirmId, setPauseConfirmId] = useState<number | null>(null);

  const {
    runNowMutation,
    toggleMutation,
    deleteMutation,
    appendKeywordsMutation,
    removeKeywordsMutation,
    isPendingTaskId,
  } = mutations;

  const activeTaskForRemove = tasks.find((t) => t.id === removeModalTaskId);

  return (
    <div className='card'>
      <div className='card-title'>
        <span>{title}</span>
        <button type='button' className='btn btn-outline btn-sm' onClick={() => refetch()}>
          🔄 刷新列表
        </button>
      </div>

      <div className='table-container'>
        {isLoading ? (
          <div style={{ textAlign: 'center', padding: '30px', color: 'var(--text-muted)' }}>加载任务中...</div>
        ) : tasks.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '30px', color: 'var(--text-muted)' }}>{emptyText}</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>任务名称</th>
                <th>关键词详情</th>
                <th>状态</th>
                <th>对应飞书表格</th>
                <th>模式</th>
                <th>调度频率</th>
                <th>上次执行</th>
                <th style={{ textAlign: 'center' }}>操作</th>
              </tr>
            </thead>
            <tbody>
              {tasks.map((t) => {
                const isPending = isPendingTaskId(t.id);
                return (
                  <tr key={t.id}>
                    <td>
                      <strong>{t.name}</strong>
                      <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>ID: #{t.id}</div>
                    </td>
                    <td style={{ maxWidth: '280px' }}>
                      <div style={{ fontWeight: 600, color: 'var(--text-secondary)' }}>
                        有效监控: {t.keywords?.length || 0} 个词
                      </div>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px', marginTop: '2px' }}>
                        {t.keywords?.slice(0, 4).map((kw: string) => (
                          <span key={kw} className='badge badge-gray' style={{ fontSize: '11px' }}>
                            {kw}
                          </span>
                        ))}
                        {t.keywords?.length > 4 && (
                          <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>+{t.keywords.length - 4}...</span>
                        )}
                      </div>
                    </td>
                    <td>
                      <span className={'badge ' + (t.status === 'active' ? 'badge-success' : 'badge-gray')}>
                        {t.status === 'active' ? '正常运行' : '已暂停'}
                      </span>
                    </td>
                    <td>
                      {t.spreadsheet_url ? (
                        <a
                          href={t.spreadsheet_url}
                          target='_blank'
                          rel='noreferrer'
                          style={{ color: 'var(--primary)', fontWeight: 500, textDecoration: 'none' }}
                        >
                          查看飞书表格 ↗
                        </a>
                      ) : '-'}
                    </td>
                    <td>{t.update_mode === 'append' ? '增量追加' : '全量覆写'}</td>
                    <td>
                      <span className='freq-tag' title={t.rrule}>
                        <Clock size={12} className='icon' style={{ opacity: 0.7 }} />
                        <span>{formatRruleText(t.rrule)}</span>
                      </span>
                    </td>
                    <td>
                      <div>{t.last_run_at ? t.last_run_at.substring(0, 16).replace('T', ' ') : '-'}</div>
                      {t.last_status && (
                        <span className={'badge ' + (t.last_status === 'success' ? 'badge-success' : 'badge-danger')} style={{ marginTop: '2px' }}>
                          {t.last_status === 'success' ? '成功' : '失败'}
                        </span>
                      )}
                    </td>
                    <td style={{ textAlign: 'center' }}>
                      <div style={{ display: 'inline-flex', gap: '6px' }}>
                        <button
                          type='button'
                          className='btn btn-outline btn-sm'
                          disabled={isPending}
                          onClick={() => runNowMutation.mutate(t.id)}
                        >
                          ⚡ 立即同步
                        </button>
                        <button
                          type='button'
                          className='btn btn-outline btn-sm'
                          disabled={isPending}
                          onClick={() => {
                            if (t.status === 'active') {
                              setPauseConfirmId(t.id);
                            } else {
                              toggleMutation.mutate(t.id);
                            }
                          }}
                        >
                          {t.status === 'active' ? '暂停' : '恢复'}
                        </button>
                        <button
                          type='button'
                          className='btn btn-outline btn-sm'
                          disabled={isPending}
                          onClick={() => {
                            setAppendModalTaskId(t.id);
                            setAppendWordsInput('');
                          }}
                        >
                          + 补词
                        </button>
                        <button
                          type='button'
                          className='btn btn-outline btn-sm'
                          disabled={isPending}
                          onClick={() => {
                            setRemoveModalTaskId(t.id);
                            setRemoveWordSelect([]);
                          }}
                        >
                          - 删词
                        </button>
                        <button
                          type='button'
                          className='btn btn-danger btn-sm'
                          disabled={isPending}
                          onClick={() => setDeleteConfirmId(t.id)}
                        >
                          归档
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {/* 补词 Dialog */}
      <Dialog
        isOpen={appendModalTaskId !== null}
        onClose={() => setAppendModalTaskId(null)}
        title='追加监控关键词'
        width='460px'
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
          <div>
            <label style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text)', display: 'block', marginBottom: '6px' }}>
              新增关键词 (换行或逗号分隔)
            </label>
            <textarea
              rows={4}
              className='form-control'
              placeholder='每行一个关键词，支持中文标点逗号分隔'
              value={appendWordsInput}
              onChange={(e) => setAppendWordsInput(e.target.value)}
            />
          </div>
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
            <button className='btn btn-outline' type='button' onClick={() => setAppendModalTaskId(null)}>
              取消
            </button>
            <button
              className='btn btn-primary'
              type='button'
              disabled={appendKeywordsMutation.isPending || !appendWordsInput.trim()}
              onClick={() => {
                if (!appendModalTaskId) return;
                const kws = appendWordsInput.split(/[\n,，]+/).map((k) => k.trim()).filter(Boolean);
                if (kws.length === 0) return;
                appendKeywordsMutation.mutate({ taskId: appendModalTaskId, keywords: kws }, {
                  onSuccess: () => setAppendModalTaskId(null),
                });
              }}
            >
              {appendKeywordsMutation.isPending ? '追加中...' : '确认追加'}
            </button>
          </div>
        </div>
      </Dialog>

      {/* 删词 Dialog */}
      <Dialog
        isOpen={removeModalTaskId !== null}
        onClose={() => setRemoveModalTaskId(null)}
        title='移除监控关键词'
        width='460px'
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
          <div style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
            勾选要从任务中移除的词：
          </div>
          <div style={{ maxHeight: '200px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '6px' }}>
            {activeTaskForRemove?.keywords?.map((kw: string) => (
              <label key={kw} style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px', cursor: 'pointer' }}>
                <input
                  type='checkbox'
                  checked={removeWordSelect.includes(kw)}
                  onChange={(e) => {
                    if (e.target.checked) setRemoveWordSelect([...removeWordSelect, kw]);
                    else setRemoveWordSelect(removeWordSelect.filter((k) => k !== kw));
                  }}
                />
                {kw}
              </label>
            ))}
          </div>
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
            <button className='btn btn-outline' type='button' onClick={() => setRemoveModalTaskId(null)}>
              取消
            </button>
            <button
              className='btn btn-danger'
              type='button'
              disabled={removeKeywordsMutation.isPending || removeWordSelect.length === 0}
              onClick={() => {
                if (!removeModalTaskId || removeWordSelect.length === 0) return;
                removeKeywordsMutation.mutate({ taskId: removeModalTaskId, keywords: removeWordSelect }, {
                  onSuccess: () => setRemoveModalTaskId(null),
                });
              }}
            >
              {removeKeywordsMutation.isPending ? '移除中...' : '确认移除选中词'}
            </button>
          </div>
        </div>
      </Dialog>

      {/* 暂停确认 Dialog */}
      <Dialog
        isOpen={pauseConfirmId !== null}
        onClose={() => setPauseConfirmId(null)}
        title='确认暂停任务'
        width='400px'
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
          <p style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
            确定暂停该任务吗？暂停后将停止定时自动触发，可随时在列表恢复运行。
          </p>
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
            <button className='btn btn-outline' type='button' onClick={() => setPauseConfirmId(null)}>
              取消
            </button>
            <button
              className='btn btn-outline'
              type='button'
              disabled={toggleMutation.isPending}
              onClick={() => {
                if (!pauseConfirmId) return;
                toggleMutation.mutate(pauseConfirmId, {
                  onSuccess: () => setPauseConfirmId(null),
                });
              }}
            >
              {toggleMutation.isPending ? '处理中...' : '确认暂停'}
            </button>
          </div>
        </div>
      </Dialog>

      {/* 归档删除确认 Dialog */}
      <Dialog
        isOpen={deleteConfirmId !== null}
        onClose={() => setDeleteConfirmId(null)}
        title='确认归档删除任务'
        width='400px'
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
          <p style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
            确定归档并删除此任务吗？飞书表格内容将保留，但后续将不再触发自动同步。
          </p>
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
            <button className='btn btn-outline' type='button' onClick={() => setDeleteConfirmId(null)}>
              取消
            </button>
            <button
              className='btn btn-danger'
              type='button'
              disabled={deleteMutation.isPending}
              onClick={() => {
                if (!deleteConfirmId) return;
                deleteMutation.mutate(deleteConfirmId, {
                  onSuccess: () => setDeleteConfirmId(null),
                });
              }}
            >
              {deleteMutation.isPending ? '归档中...' : '确认归档删除'}
            </button>
          </div>
        </div>
      </Dialog>
    </div>
  );
};
