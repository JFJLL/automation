import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { Info, Check, AlertTriangle, ArrowRight, RotateCw } from 'lucide-react';
import { fetchJson } from '@/shared/api/client';
import { useToast } from '@/shared/components/Toast';

export const ImportPage: React.FC = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { showSuccess, showError } = useToast();

  const [platform, setPlatform] = useState<string>('jzt');
  const [subAccountId, setSubAccountId] = useState<string>('');
  const [file, setFile] = useState<File | null>(null);
  const [analyzedSheets, setAnalyzedSheets] = useState<any[]>([]);
  const [selectedSheetIndices, setSelectedSheetIndices] = useState<number[]>([0]);

  // 任务配置项
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

  // 获取最近的同步任务
  const { data: recentTasks = [] } = useQuery<any[]>({
    queryKey: ['syncTasks'],
    queryFn: () => fetchJson('/api/tasks'),
  });

  // 上传 Excel 样本
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
      setSelectedSheetIndices(res.sheets.map((_, i) => i));
      if (!taskName && res.filename) {
        setTaskName(res.filename.replace(/\.[^/.]+$/, '') + '_自动同步');
      }
      showSuccess(`成功解析 ${res.sheets.length} 个工作表`);
    },
    onError: (err: any) => {
      showError(err.message || 'Excel 解析失败');
    },
  });

  // 平台预览
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

  // 创建同步任务
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

  const currentStep = !file ? 1 : analyzedSheets.length === 0 ? 2 : !previewMutation.data ? 3 : 4;

  return (
    <>
      <div className="page-heading">
        <h2>新建同步任务</h2>
        <p>按照以下步骤完成设置，将广告投放数据自动同步到飞书</p>
      </div>

      {/* 原版步骤条 */}
      <div className="workflow-steps" aria-label="任务创建进度">
        <div className={`workflow-step ${currentStep >= 1 ? 'active' : ''}`}>
          <span className="step-index">1</span>
          <span>选择投放平台</span>
        </div>
        <span className="step-line" />
        <div className={`workflow-step ${currentStep >= 2 ? 'active' : ''}`}>
          <span className="step-index">2</span>
          <span>上传 Excel 数据样本</span>
        </div>
        <span className="step-line" />
        <div className={`workflow-step ${currentStep >= 3 ? 'active' : ''}`}>
          <span className="step-index">3</span>
          <span>核验数据</span>
        </div>
        <span className="step-line" />
        <div className={`workflow-step ${currentStep >= 4 ? 'active' : ''}`}>
          <span className="step-index">4</span>
          <span>创建同步任务</span>
        </div>
      </div>

      <div className="import-dashboard-grid">
        <div className="card workflow-primary">
          {/* 第 1 步：选择投放平台 */}
          <section className="workflow-section">
            <div className="section-heading">
              <span className="step-index">1</span>
              <div>
                <h3>选择投放平台</h3>
                <p>请选择需要同步的广告平台</p>
              </div>
            </div>
            <div className="platform-selector">
              <div
                className={`platform-card ${platform === 'jzt' ? 'selected' : ''}`}
                onClick={() => {
                  setPlatform('jzt');
                  if (file) uploadMutation.mutate(file);
                }}
              >
                <img className="platform-logo" src="/static/assets/platform-jzt.png" alt="京准通" />
                <div className="title">京准通</div>
                <div className="desc">京东达人/小红盟报表<br />(25列日明细)</div>
              </div>
              <div
                className={`platform-card ${platform === 'taobao' ? 'selected' : ''}`}
                onClick={() => {
                  setPlatform('taobao');
                  if (file) uploadMutation.mutate(file);
                }}
              >
                <img className="platform-logo" src="/static/assets/platform-taobao.png" alt="淘宝星河" />
                <div className="title">淘宝星河</div>
                <div className="desc">小红星达人效果报表<br />(内容/任务维度)</div>
              </div>
              <div
                className={`platform-card ${platform === 'juguang' ? 'selected' : ''}`}
                onClick={() => {
                  setPlatform('juguang');
                  if (file) uploadMutation.mutate(file);
                }}
              >
                <img className="platform-logo" src="/static/assets/platform-juguang.png" alt="小红书聚光" />
                <div className="title">小红书聚光</div>
                <div className="desc">小红书后台报表<br />(创意/定向/关键词/账户)</div>
              </div>
            </div>

            {platform === 'juguang' && (
              <div style={{ marginTop: '16px', padding: '14px', background: '#fff8f8', border: '1px solid #f9d2d5', borderRadius: '8px' }}>
                <label style={{ fontSize: '13px', fontWeight: 600, color: '#82222b', display: 'block', marginBottom: '8px' }}>
                  选择聚光子账号
                </label>
                <select
                  value={subAccountId}
                  onChange={(e) => setSubAccountId(e.target.value)}
                  className="form-control"
                  style={{ maxWidth: '400px' }}
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
          </section>

          {/* 第 2 步：上传 Excel */}
          <section className="workflow-section">
            <div className="section-heading">
              <span className="step-index">2</span>
              <div>
                <h3>上传 Excel 数据样本</h3>
                <p>请上传广告平台导出的 Excel 报表样本，系统将自动解析表头与数据结构</p>
              </div>
            </div>
            <label
              className="upload-box"
              style={{ display: 'block', cursor: 'pointer' }}
            >
              <input type="file" accept=".xlsx,.xls" style={{ display: 'none' }} onChange={handleFileChange} />
              <div className="upload-file-icon">X</div>
              <div className="upload-title">{file ? file.name : '点击或拖拽上传 Excel 文件'}</div>
              <div className="upload-desc">支持 .xlsx、.xls 格式，建议使用近 30 行样本数据，文件不超过 50MB</div>
            </label>
            <div className="upload-note">
              <Info className="icon" size={14} />
              <span>上传后系统将自动解析表头字段、数据类型，并进行格式校验</span>
            </div>
          </section>
        </div>

        {/* 右侧指引 Rail */}
        <aside className="insight-rail">
          <section className="rail-card">
            <div className="rail-title">
              <h3>最近的同步任务</h3>
              <button className="rail-link" type="button" onClick={() => navigate('/tasks')}>
                查看更多 ›
              </button>
            </div>
            {recentTasks.length === 0 ? (
              <div className="recent-empty">任务创建后会显示在这里<br />便于快速查看运行状态</div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {recentTasks.slice(0, 3).map((t) => (
                  <div key={t.id} style={{ fontSize: '12px', padding: '6px 0', borderBottom: '1px solid #f1f5f9' }}>
                    <div style={{ fontWeight: 600, color: 'var(--text)' }}>{t.name}</div>
                    <div style={{ color: 'var(--text-muted)', fontSize: '11px' }}>{t.platform} · {t.update_mode}</div>
                  </div>
                ))}
              </div>
            )}
          </section>

          <section className="rail-card">
            <div className="rail-title">
              <h3>操作指引</h3>
            </div>
            <div className="guide-list">
              <div className="guide-item">
                <span className="num">1</span>
                <div>
                  <strong>选择投放平台</strong>
                  <p>根据需要同步的数据来源，选择对应平台</p>
                </div>
              </div>
              <div className="guide-item">
                <span className="num">2</span>
                <div>
                  <strong>上传 Excel 数据样本</strong>
                  <p>使用平台导出的报表文件，系统将自动解析字段</p>
                </div>
              </div>
              <div className="guide-item">
                <span className="num">3</span>
                <div>
                  <strong>核验数据</strong>
                  <p>确认字段映射关系与数据格式是否正确</p>
                </div>
              </div>
              <div className="guide-item">
                <span className="num">4</span>
                <div>
                  <strong>创建同步任务</strong>
                  <p>配置飞书表格、同步频率等信息</p>
                </div>
              </div>
            </div>
          </section>
        </aside>
      </div>

      {/* 第 3 步：工作表分析与实体确认 */}
      {analyzedSheets.length > 0 && (
        <div className="card" id="sheetAnalysisCard" style={{ animation: 'uiFadeUp .28s both' }}>
          <div className="card-title">第三步：工作表分析与实体确认</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <div style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
              已解析 {analyzedSheets.length} 个工作表，勾选需要包含进同步计划的 Sheet：
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '12px' }}>
              {analyzedSheets.map((s, idx) => {
                const isSelected = selectedSheetIndices.includes(idx);
                return (
                  <div
                    key={s.sheet_title}
                    onClick={() => handleToggleSheet(idx)}
                    style={{
                      padding: '14px 16px',
                      borderRadius: '8px',
                      border: '1.5px solid ' + (isSelected ? 'var(--primary)' : 'var(--border)'),
                      background: isSelected ? 'var(--primary-light)' : '#ffffff',
                      cursor: 'pointer',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '6px',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <strong style={{ fontSize: '14px', color: isSelected ? 'var(--primary)' : 'var(--text)' }}>
                        {s.sheet_title}
                      </strong>
                      <span style={{ fontSize: '12px', color: isSelected ? 'var(--primary)' : 'var(--text-muted)' }}>
                        {isSelected ? '✓ 已选中' : '未选择'}
                      </span>
                    </div>
                    <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                      ID 列: <strong>{s.id_column || '未识别'}</strong> · 日期: <strong>{s.date_column || '未识别'}</strong>
                    </div>
                    <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                      识别到实体数: <strong>{s.detected_entity_ids?.length || 0} 个</strong>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {/* 第 4 步：平台接口预览 */}
      {analyzedSheets.length > 0 && (
        <div className="card" id="previewCard" style={{ animation: 'uiFadeUp .28s both' }}>
          <div className="card-title">
            <span>第四步：调取平台接口数据预览</span>
            <button
              type="button"
              className="btn btn-primary btn-sm"
              onClick={() => previewMutation.mutate()}
              disabled={previewMutation.isPending}
            >
              🔄 重新测试抓取
            </button>
          </div>

          {previewMutation.data ? (
            <div className="table-container" style={{ maxHeight: '280px', overflowY: 'auto' }}>
              <table>
                <thead>
                  <tr>
                    {previewMutation.data.headers.map((h: string, i: number) => (
                      <th key={i}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {previewMutation.data.rows.slice(0, 8).map((row: any[], rIdx: number) => (
                    <tr key={rIdx}>
                      {row.map((c: any, cIdx: number) => (
                        <td key={cIdx}>{c !== null && c !== undefined ? String(c) : '-'}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div style={{ padding: '24px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '13px' }}>
              点击上方按钮测试调取目标平台（{platform === 'jzt' ? '京准通' : platform === 'taobao' ? '淘宝星河' : '小红书聚光'}）接口并核验字段映射。
            </div>
          )}
        </div>
      )}

      {/* 第 5 步：创建任务与定时配置 */}
      {analyzedSheets.length > 0 && (
        <div className="card" id="scheduleConfigCard" style={{ animation: 'uiFadeUp .28s both' }}>
          <div className="card-title">第五步：创建飞书表格并配置定时自动同步</div>

          <div className="form-row">
            <div className="form-group" style={{ flex: 2 }}>
              <label>飞书表格名称</label>
              <input
                type="text"
                className="form-control"
                value={taskName}
                onChange={(e) => setTaskName(e.target.value)}
              />
            </div>
            <div className="form-group">
              <label>更新方式</label>
              <select
                className="form-control"
                value={updateMode}
                onChange={(e) => setUpdateMode(e.target.value)}
              >
                <option value="append">增量更新（自动校准并防重）</option>
                <option value="overwrite">全量覆盖（滚动窗口覆写）</option>
              </select>
            </div>
            <div className="form-group" style={{ maxWidth: '140px' }}>
              <label>回溯校准天数</label>
              <input
                type="number"
                min="0"
                max="30"
                className="form-control"
                value={calibrationDays}
                onChange={(e) => setCalibrationDays(parseInt(e.target.value) || 0)}
              />
            </div>
          </div>

          <div style={{ border: '1px solid var(--border)', borderRadius: '8px', padding: '18px', background: '#fafbfc', margin: '16px 0' }}>
            <label style={{ fontSize: '14px', fontWeight: 600, display: 'block', marginBottom: '8px' }}>
              ⏰ 自动化同步周期 (RRULE)
            </label>
            <select
              className="form-control"
              value={rrule}
              onChange={(e) => setRrule(e.target.value)}
              style={{ maxWidth: '360px' }}
            >
              <option value="RRULE:FREQ=DAILY;BYHOUR=9;BYMINUTE=0">每天 09:00 执行</option>
              <option value="RRULE:FREQ=DAILY;BYHOUR=12;BYMINUTE=30">每天 12:30 执行 (推荐，T-1数据)</option>
              <option value="RRULE:FREQ=DAILY;BYHOUR=18;BYMINUTE=0">每天 18:00 执行</option>
              <option value="RRULE:FREQ=WORKDAY;BYHOUR=9;BYMINUTE=30">法定工作日 09:30 执行</option>
            </select>
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px' }}>
            <button
              type="button"
              className="btn btn-primary"
              disabled={createTaskMutation.isPending || !taskName.trim() || selectedSheetIndices.length === 0}
              onClick={() => createTaskMutation.mutate()}
            >
              {createTaskMutation.isPending ? '创建中…' : '🚀 立即生成飞书表格并启用定时任务'}
            </button>
          </div>
        </div>
      )}
    </>
  );
};

