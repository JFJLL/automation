import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { UploadCloud, CheckCircle, AlertCircle, FileSpreadsheet, ArrowRight, Play } from 'lucide-react';
import { fetchJson } from '@/shared/api/client';
import { Button } from '@/shared/components/Button';
import { useToast } from '@/shared/components/Toast';

export const ImportPage: React.FC = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { showSuccess, showError } = useToast();

  const [platform, setPlatform] = useState<string>('jzt');
  const [subAccountId, setSubAccountId] = useState<string>('');
  const [file, setFile] = useState<File | null>(null);
  const [analyzedSheets, setAnalyzedSheets] = useState<any[]>([]);
  const [selectedSheetIdx, setSelectedSheetIdx] = useState<number>(0);
  const [taskName, setTaskName] = useState<string>('');
  const [updateMode, setUpdateMode] = useState<string>('append');
  const [calibrationDays, setCalibrationDays] = useState<number>(2);
  const [rrule, setRrule] = useState<string>('RRULE:FREQ=DAILY;BYHOUR=9;BYMINUTE=0');

  // 获取子账号列表
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
      setSelectedSheetIdx(0);
      if (!taskName && res.filename) {
        setTaskName(res.filename.replace(/\.[^/.]+$/, '') + '_自动同步');
      }
      showSuccess(`成功解析 ${res.sheets.length} 个工作表`);
    },
    onError: (err: any) => {
      showError(err.message || 'Excel 解析失败');
    },
  });

  // 创建任务
  const createTaskMutation = useMutation({
    mutationFn: async () => {
      const currentSheet = analyzedSheets[selectedSheetIdx];
      const payload = {
        task_name: taskName,
        platform,
        sub_account_id: platform === 'juguang' ? subAccountId : null,
        sub_account_name: platform === 'juguang' ? subaccounts.find(s => s.id === subAccountId)?.name : null,
        update_mode: updateMode,
        calibration_days: calibrationDays,
        rrule,
        write_initial_data: true,
        sheets: [
          {
            sheet_title: currentSheet.sheet_title,
            dimension: currentSheet.dimension || '',
            id_column: currentSheet.id_column,
            date_column: currentSheet.date_column,
            headers: currentSheet.headers,
            column_mapping: currentSheet.column_mapping || [],
            entity_ids: currentSheet.detected_entity_ids || [],
            initial_rows: currentSheet.sample_rows || [],
          },
        ],
      };
      return fetchJson<{ task_id: number; spreadsheet_url: string }>('/api/create_task', {
        method: 'POST',
        body: JSON.stringify(payload),
      });
    },
    onSuccess: (res) => {
      showSuccess('数据同步任务创建成功，已建立飞书在线表格');
      queryClient.invalidateQueries({ queryKey: ['syncTasks'] });
      navigate('/tasks');
    },
    onError: (err: any) => {
      showError(err.message || '创建任务失败');
    },
  });

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

      {/* 第一步：选择目标平台 */}
      <div style={{ backgroundColor: '#ffffff', borderRadius: '12px', padding: '20px', border: '1px solid #e2e8f0' }}>
        <h3 style={{ fontSize: '15px', fontWeight: 600, color: '#0f172a', marginBottom: '14px' }}>
          1. 选择数据源平台
        </h3>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '14px' }}>
          {[
            { id: 'jzt', name: '京准通 (京东)', desc: '按达人/推广单元任务同步' },
            { id: 'taobao', name: '淘宝星河', desc: '红宝/星河内容与订单归因' },
            { id: 'juguang', name: '小红书聚光', desc: '支持多子账号广告报表' },
          ].map((p) => {
            const isSel = platform === p.id;
            return (
              <div
                key={p.id}
                onClick={() => {
                  setPlatform(p.id);
                  if (file) uploadMutation.mutate(file);
                }}
                style={{
                  padding: '16px',
                  borderRadius: '8px',
                  cursor: 'pointer',
                  border: '2px solid ' + (isSel ? '#ea3445' : '#e2e8f0'),
                  backgroundColor: isSel ? '#fef2f2' : '#ffffff',
                  transition: 'all 0.15s ease',
                }}
              >
                <div style={{ fontWeight: 600, fontSize: '15px', color: isSel ? '#ea3445' : '#0f172a' }}>
                  {p.name}
                </div>
                <div style={{ fontSize: '12px', color: '#64748b', marginTop: '4px' }}>{p.desc}</div>
              </div>
            );
          })}
        </div>

        {platform === 'juguang' && (
          <div style={{ marginTop: '16px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
            <label style={{ fontSize: '13px', fontWeight: 600, color: '#334155' }}>聚光子账号</label>
            <select
              value={subAccountId}
              onChange={(e) => setSubAccountId(e.target.value)}
              style={{
                padding: '8px 12px',
                borderRadius: '6px',
                border: '1px solid #cbd5e1',
                fontSize: '14px',
                maxWidth: '400px',
              }}
            >
              <option value="">默认主账号 / 全局凭据</option>
              {subaccounts.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name} ({s.id})
                </option>
              ))}
            </select>
          </div>
        )}
      </div>

      {/* 第二步：上传 Excel */}
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
            transition: 'border 0.2s',
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

      {/* 第三步：Sheet 识别与配置 */}
      {analyzedSheets.length > 0 && (
        <div style={{ backgroundColor: '#ffffff', borderRadius: '12px', padding: '20px', border: '1px solid #e2e8f0' }}>
          <h3 style={{ fontSize: '15px', fontWeight: 600, color: '#0f172a', marginBottom: '14px' }}>
            3. 配置同步任务与调度
          </h3>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            {analyzedSheets.length > 1 && (
              <div style={{ display: 'flex', gap: '8px' }}>
                {analyzedSheets.map((s, idx) => (
                  <button
                    key={s.sheet_title}
                    onClick={() => setSelectedSheetIdx(idx)}
                    style={{
                      padding: '6px 12px',
                      borderRadius: '6px',
                      border: '1px solid ' + (selectedSheetIdx === idx ? '#ea3445' : '#cbd5e1'),
                      backgroundColor: selectedSheetIdx === idx ? '#fef2f2' : '#ffffff',
                      color: selectedSheetIdx === idx ? '#ea3445' : '#475569',
                      fontSize: '13px',
                      cursor: 'pointer',
                    }}
                  >
                    {s.sheet_title}
                  </button>
                ))}
              </div>
            )}

            {/* 实体识别详情 */}
            {analyzedSheets[selectedSheetIdx] && (
              <div style={{ padding: '12px 16px', backgroundColor: '#f8fafc', borderRadius: '8px', fontSize: '13px' }}>
                <div style={{ display: 'flex', gap: '20px', color: '#475569' }}>
                  <span>
                    工作表：<strong>{analyzedSheets[selectedSheetIdx].sheet_title}</strong>
                  </span>
                  <span>
                    ID 列：<strong>{analyzedSheets[selectedSheetIdx].id_column}</strong>
                  </span>
                  <span>
                    已识别实体：<strong>{analyzedSheets[selectedSheetIdx].detected_entity_ids?.length || 0} 个</strong>
                  </span>
                </div>
              </div>
            )}

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

            <div style={{ marginTop: '12px', display: 'flex', justifyContent: 'flex-end' }}>
              <Button
                size="lg"
                variant="primary"
                onClick={() => createTaskMutation.mutate()}
                loading={createTaskMutation.isPending}
                disabled={!taskName}
              >
                创建同步任务并建立飞书表 <ArrowRight size={16} />
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

