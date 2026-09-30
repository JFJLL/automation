import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { UploadCloud, ArrowRight } from 'lucide-react';
import { fetchJson } from '@/shared/api/client';
import { Button } from '@/shared/components/Button';
import { useToast } from '@/shared/components/Toast';
import { PlatformSelector } from '../components/PlatformSelector';
import { SheetSelector } from '../components/SheetSelector';
import { PreviewPanel } from '../components/PreviewPanel';

export const ImportPage: React.FC = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { showSuccess, showError, showInfo } = useToast();

  const [platform, setPlatform] = useState<string>('jzt');
  const [subAccountId, setSubAccountId] = useState<string>('');
  const [file, setFile] = useState<File | null>(null);
  const [analyzedSheets, setAnalyzedSheets] = useState<any[]>([]);
  const [selectedSheetIndices, setSelectedSheetIndices] = useState<number[]>([0]);
  const [taskName, setTaskName] = useState<string>('');
  const [updateMode, setUpdateMode] = useState<string>('append');
  const [calibrationDays, setCalibrationDays] = useState<number>(2);
  const [rrule, setRrule] = useState<string>('RRULE:FREQ=DAILY;BYHOUR=9;BYMINUTE=0');

  // 获取聚光子账号
  const { data: subaccounts = [] } = useQuery<Array<{ id: string; name: string }>>({
    queryKey: ['subaccounts'],
    queryFn: () => fetchJson('/api/platforms/juguang/subaccounts'),
    enabled: platform === 'juguang',
  });

  // 上传文件并分析
  const uploadMutation = useMutation({
    mutationFn: async (uploadFile: File) => {
      const formData = new FormData();
      formData.append('file', uploadFile);
      formData.append('selected_platform', platform);
      return fetchJson<{ sheets: any[]; filename: string }>('/api/upload', {
        method: 'POST',
        body: formData,
      });
    },
    onSuccess: (res) => {
      setAnalyzedSheets(res.sheets);
      setSelectedSheetIndices(res.sheets.map((_, i) => i)); // 默认全选
      if (!taskName && res.filename) {
        setTaskName(res.filename.replace(/\.[^/.]+$/, '') + '_自动同步');
      }
      showSuccess(`成功解析 ${res.sheets.length} 个工作表`);
    },
    onError: (err: any) => {
      showError(err.message || 'Excel 解析失败');
    },
  });

  // 抓取真实数据 Preview (Section 二十一 parity)
  const previewMutation = useMutation({
    mutationFn: async () => {
      const firstSheet = analyzedSheets[selectedSheetIndices[0] || 0];
      if (!firstSheet) throw new Error('未选择有效工作表');
      
      const today = new Date();
      const endStr = today.toISOString().split('T')[0];
      const startDt = new Date(today.getTime() - 7 * 86400 * 1000);
      const startStr = startDt.toISOString().split('T')[0];

      return fetchJson<any>('/api/preview', {
        method: 'POST',
        body: JSON.stringify({
          platform,
          sheet_title: firstSheet.sheet_title,
          headers: firstSheet.headers || [],
          entity_ids: firstSheet.detected_entity_ids || [],
          id_column: firstSheet.id_column || '',
          date_column: firstSheet.date_column || '',
          dimension: firstSheet.dimension || '',
          start_date: startStr,
          end_date: endStr,
          sub_account_id: platform === 'juguang' ? subAccountId : null,
        }),
      });
    },
    onSuccess: (res) => {
      showSuccess(`成功从目标平台获取到 ${res.total_fetched} 行预览数据`);
    },
    onError: (err: any) => {
      showError(err.message || '预览抓取失败');
    },
  });

  // 创建任务 (支持多 Sheet 勾选与真实预览数据提交)
  const createTaskMutation = useMutation({
    mutationFn: async () => {
      if (selectedSheetIndices.length === 0) {
        throw new Error('请至少勾选一个工作表');
      }

      const previewRows = previewMutation.data?.rows || [];

      const sheetsPayload = selectedSheetIndices.map((idx) => {
        const s = analyzedSheets[idx];
        return {
          sheet_title: s.sheet_title,
          dimension: s.dimension || '',
          id_column: s.id_column,
          date_column: s.date_column,
          headers: s.headers,
          column_mapping: s.column_mapping || [],
          entity_ids: s.detected_entity_ids || [],
          initial_rows: idx === 0 && previewRows.length > 0 ? previewRows : (s.sample_rows || []),
        };
      });

      const payload = {
        task_name: taskName,
        platform,
        sub_account_id: platform === 'juguang' ? subAccountId : null,
        sub_account_name: platform === 'juguang' ? subaccounts.find((s) => s.id === subAccountId)?.name : null,
        update_mode: updateMode,
        calibration_days: calibrationDays,
        rrule,
        write_initial_data: true,
        sheets: sheetsPayload,
      };

      return fetchJson<{ task_id: number; spreadsheet_url: string }>('/api/create_task', {
        method: 'POST',
        body: JSON.stringify(payload),
      });
    },
    onSuccess: () => {
      showSuccess('数据同步任务创建成功！已自动建立飞书表格与调度');
      queryClient.invalidateQueries({ queryKey: ['syncTasks'] });
      navigate('/tasks');
    },
    onError: (err: any) => {
      showError(err.message || '创建任务失败');
    },
  });

  const handleToggleSheet = (idx: number) => {
    setSelectedSheetIndices((prev) =>
      prev.includes(idx) ? prev.filter((i) => i !== idx) : [...prev, idx]
    );
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const selected = e.target.files[0];
      setFile(selected);
      uploadMutation.mutate(selected);
    }
  };

  return (
    <div style={{ maxWidth: '1000px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '24px' }}>
      <div>
        <h2 style={{ fontSize: '20px', fontWeight: 700, color: '#0f172a' }}>导入报表并创建同步任务</h2>
        <p style={{ fontSize: '13px', color: '#64748b', marginTop: '4px' }}>
          上传已有业务 Excel，系统将智能提取实体 ID、匹配维度并初始化飞书在线报表
        </p>
      </div>

      {/* 1. 选择数据源平台 */}
      <PlatformSelector
        platform={platform}
        setPlatform={(p) => {
          setPlatform(p);
          if (file) uploadMutation.mutate(file);
        }}
        subAccountId={subAccountId}
        setSubAccountId={setSubAccountId}
        subaccounts={subaccounts}
      />

      {/* 2. 上传 Excel */}
      <div style={{ backgroundColor: '#ffffff', borderRadius: '12px', padding: '20px', border: '1px solid #e2e8f0' }}>
        <h3 style={{ fontSize: '15px', fontWeight: 600, color: '#0f172a', marginBottom: '14px' }}>
          2. 上传数据模板 Excel
        </h3>
        <label
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '36px',
            border: '2px dashed #cbd5e1',
            borderRadius: '8px',
            cursor: 'pointer',
            backgroundColor: '#f8fafc',
          }}
        >
          <UploadCloud size={36} color="#ea3445" />
          <div style={{ marginTop: '10px', fontSize: '14px', fontWeight: 500, color: '#334155' }}>
            {file ? file.name : '点击或拖拽上传 .xlsx 报表文件'}
          </div>
          <div style={{ fontSize: '12px', color: '#94a3b8', marginTop: '4px' }}>支持包含多工作表的 Excel 报表</div>
          <input type="file" accept=".xlsx,.xls" onChange={handleFileChange} style={{ display: 'none' }} />
        </label>
      </div>

      {/* 3. Sheet 识别、预览与任务配置 */}
      {analyzedSheets.length > 0 && (
        <div style={{ backgroundColor: '#ffffff', borderRadius: '12px', padding: '20px', border: '1px solid #e2e8f0', display: 'flex', flexDirection: 'column', gap: '20px' }}>
          <h3 style={{ fontSize: '15px', fontWeight: 600, color: '#0f172a' }}>
            3. 配置同步任务与调度
          </h3>

          {/* 多 Sheet 勾选选择器 */}
          <SheetSelector
            sheets={analyzedSheets}
            selectedSheetIndices={selectedSheetIndices}
            onToggleSheet={handleToggleSheet}
            selectedPlatform={platform}
          />

          {/* 真实平台数据 Preview */}
          <PreviewPanel
            onFetchPreview={() => previewMutation.mutate()}
            isLoading={previewMutation.isPending}
            previewResult={previewMutation.data}
          />

          {/* 任务名称 */}
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

          {/* 更新模式与回溯天数 */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
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
                <option value="append">增量更新 (自动校准并防重)</option>
                <option value="overwrite">全量覆写 (滚动窗口)</option>
              </select>
            </div>

            <div>
              <label style={{ fontSize: '13px', fontWeight: 600, color: '#334155', display: 'block', marginBottom: '6px' }}>
                回溯校准天数
              </label>
              <input
                type="number"
                min="0"
                max="30"
                value={calibrationDays}
                onChange={(e) => setCalibrationDays(parseInt(e.target.value) || 0)}
                style={{
                  width: '100%',
                  padding: '9px 12px',
                  borderRadius: '6px',
                  border: '1px solid #cbd5e1',
                  fontSize: '14px',
                }}
              />
            </div>
          </div>

          {/* 定时频率 */}
          <div>
            <label style={{ fontSize: '13px', fontWeight: 600, color: '#334155', display: 'block', marginBottom: '6px' }}>
              执行频率 (RRULE)
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
              <option value="RRULE:FREQ=DAILY;BYHOUR=9;BYMINUTE=0">每天 09:00 执行</option>
              <option value="RRULE:FREQ=DAILY;BYHOUR=12;BYMINUTE=30">每天 12:30 执行 (T-1 推荐)</option>
              <option value="RRULE:FREQ=DAILY;BYHOUR=18;BYMINUTE=0">每天 18:00 执行</option>
              <option value="RRULE:FREQ=WORKDAY;BYHOUR=9;BYMINUTE=30">法定工作日 09:30 执行</option>
            </select>
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '10px' }}>
            <Button
              size="lg"
              variant="primary"
              onClick={() => createTaskMutation.mutate()}
              loading={createTaskMutation.isPending}
              disabled={!taskName || selectedSheetIndices.length === 0}
            >
              创建同步任务并建立飞书表 ({selectedSheetIndices.length} Sheet) <ArrowRight size={16} />
            </Button>
          </div>
        </div>
      )}
    </div>
  );
};

