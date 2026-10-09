import React from 'react';
import { AlertTriangle } from 'lucide-react';
import { Dialog } from '@/shared/components/Dialog';
import { Button } from '@/shared/components/Button';
import { SchedulePicker } from '@/shared/components/SchedulePicker';

export interface CreateKeywordTaskDialogProps {
  isOpen: boolean;
  onClose: () => void;
  taskName: string;
  setTaskName: (val: string) => void;
  updateMode: string;
  setUpdateMode: (val: string) => void;
  rrule: string;
  setRrule: (val: string) => void;
  keywordsCount: number;
  hasFailedKeywords: boolean;
  onSubmit: () => void;
  isSubmitting: boolean;
}

export const CreateKeywordTaskDialog: React.FC<CreateKeywordTaskDialogProps> = ({
  isOpen,
  onClose,
  taskName,
  setTaskName,
  updateMode,
  setUpdateMode,
  rrule,
  setRrule,
  keywordsCount,
  hasFailedKeywords,
  onSubmit,
  isSubmitting,
}) => {
  return (
    <Dialog isOpen={isOpen} onClose={onClose} title="创建关键词监控定时任务" width="460px">
      <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
        {hasFailedKeywords && (
          <div
            style={{
              padding: '10px 14px',
              backgroundColor: '#fef2f2',
              border: '1px solid #fecaca',
              borderRadius: '6px',
              fontSize: '12px',
              color: '#dc2626',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
            }}
          >
            <AlertTriangle size={15} />
            <span>当前存在获取失败的关键词，请先清理失败词项再创建定时任务。</span>
          </div>
        )}

        <div>
          <label style={{ fontSize: '13px', fontWeight: 600, color: '#334155', display: 'block', marginBottom: '6px' }}>
            任务名称
          </label>
          <input
            type="text"
            value={taskName}
            onChange={(e) => setTaskName(e.target.value)}
            style={{
              width: '100%',
              padding: '9px 12px',
              borderRadius: '6px',
              border: '1px solid #cbd5e1',
              fontSize: '14px',
            }}
          />
        </div>

        <div>
          <label style={{ fontSize: '13px', fontWeight: 600, color: '#334155', display: 'block', marginBottom: '6px' }}>
            写入模式
          </label>
          <select
            value={updateMode}
            onChange={(e) => setUpdateMode(e.target.value)}
            style={{
              width: '100%',
              padding: '9px 12px',
              borderRadius: '6px',
              border: '1px solid #cbd5e1',
              fontSize: '14px',
            }}
          >
            <option value="overwrite">全量滚动覆写 (保持最近90天滚动)</option>
            <option value="append">增量历史累加 (保留历史旧日期并右侧追加新日期)</option>
          </select>
        </div>

        <div>
          <SchedulePicker
            label="调度频率 (RRULE)"
            value={rrule}
            onChange={setRrule}
          />
        </div>

        <div style={{ fontSize: '13px', color: '#64748b' }}>
          将监控当前选中的 <strong>{keywordsCount}</strong> 个关键词。
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
          <Button variant="secondary" type="button" onClick={onClose}>
            取消
          </Button>
          <Button
            variant="primary"
            type="button"
            loading={isSubmitting}
            disabled={!taskName.trim() || hasFailedKeywords}
            onClick={onSubmit}
          >
            确认创建
          </Button>
        </div>
      </div>
    </Dialog>
  );
};

