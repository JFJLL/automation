import React from 'react';
import { AlertTriangle } from 'lucide-react';
import { Dialog } from '@/shared/components/Dialog';
import { Button } from '@/shared/components/Button';

export interface CreateLingxiTaskDialogProps {
  isOpen: boolean;
  onClose: () => void;
  taskName: string;
  setTaskName: (val: string) => void;
  rrule: string;
  setRrule: (val: string) => void;
  keywordsCount: number;
  hasFailedKeywords: boolean;
  onSubmit: () => void;
  isSubmitting: boolean;
}

export const CreateLingxiTaskDialog: React.FC<CreateLingxiTaskDialogProps> = ({
  isOpen,
  onClose,
  taskName,
  setTaskName,
  rrule,
  setRrule,
  keywordsCount,
  hasFailedKeywords,
  onSubmit,
  isSubmitting,
}) => {
  return (
    <Dialog isOpen={isOpen} onClose={onClose} title="创建灵犀关键词监控定时任务" width="460px">
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
            调度频率 (RRULE)
          </label>
          <select
            value={rrule}
            onChange={(e) => setRrule(e.target.value)}
            style={{
              width: '100%',
              padding: '9px 12px',
              borderRadius: '6px',
              border: '1px solid #cbd5e1',
              fontSize: '14px',
            }}
          >
            <option value="FREQ=DAILY;BYHOUR=9;BYMINUTE=30">每天 09:30 执行 (实时数据)</option>
            <option value="FREQ=DAILY;BYHOUR=12;BYMINUTE=30">每天 12:30 执行 (实时数据)</option>
            <option value="FREQ=DAILY;BYHOUR=18;BYMINUTE=0">每天 18:00 执行 (实时数据)</option>
            <option value="FREQ=DAILY;BYHOUR=21;BYMINUTE=0">每天 21:00 执行 (实时数据)</option>
          </select>
        </div>

        <div style={{ fontSize: '13px', color: '#64748b' }}>
          将监控当前选中的 <strong>{keywordsCount}</strong> 个关键词，每日自动在飞书表格中新增当天的日期列，实现覆盖人数增量记录。
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

