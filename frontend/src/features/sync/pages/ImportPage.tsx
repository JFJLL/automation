import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { Info, Check, AlertTriangle, ArrowRight, RotateCw, Layers, Calendar, Link2, Hash } from 'lucide-react';
import { fetchJson } from '@/shared/api/client';
import { SchedulePicker } from '@/shared/components/SchedulePicker';
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
  const [isMergeTasks, setIsMergeTasks] = useState(false);
  const [customTaskIdsInput, setCustomTaskIdsInput] = useState('');
  const [isLinkExisting, setIsLinkExisting] = useState(false);
  const [existingUrl, setExistingUrl] = useState('');
  const [newSheetTitle, setNewSheetTitle] = useState('');
  const [showInstruction, setShowInstruction] = useState(false);
  const [createErrorMsg, setCreateErrorMsg] = useState('');

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
      if (res.sheets && res.sheets.length > 0) {
        const defaultIds = res.sheets[0]?.detected_entity_ids || [];
        setCustomTaskIdsInput(defaultIds.join(', '));
      }
      showSuccess(`成功解析 ${res.sheets.length} 个工作表`);
      // 上传成功后自动触发接口数据抓取预览
      setTimeout(() => {
        previewMutation.mutate();
      }, 80);
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
      const startStr = firstSheet.next_start_date || new Date(today.getTime() - 7 * 86400 * 1000).toISOString().split('T')[0];

      return fetchJson<any>('/api/preview', {
        method: 'POST',
        body: JSON.stringify({
          platform,
          sheet_title: firstSheet.sheet_title,
          headers: firstSheet.headers || [],
          entity_ids: (isMergeTasks && customTaskIdsInput.trim()) ? customTaskIdsInput.replace(/[,，\s]+/g, ' ').split(' ').filter(Boolean) : (firstSheet.detected_entity_ids || []),
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

      const sheetsPayload = selectedSheetIndices.map((idx, sheetIdx) => {
        const s = analyzedSheets[idx];
        const histRows = s.uploaded_rows || [];
        const newRows = sheetIdx === 0 && previewRows.length > 0 ? previewRows : [];
        const combined = [...histRows, ...newRows];
        return {
          sheet_title: s.sheet_title,
          dimension: s.dimension || '',
          id_column: s.id_column,
          date_column: s.date_column,
          headers: s.headers,
          column_mapping: s.column_mapping || [],
          entity_ids: (isMergeTasks && customTaskIdsInput.trim()) ? customTaskIdsInput.replace(/[,，\s]+/g, ' ').split(' ').filter(Boolean) : (s.detected_entity_ids || []),
          initial_rows: combined.length > 0 ? combined : (s.sample_rows || []),
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
        link_existing_spreadsheet: isLinkExisting,
        existing_spreadsheet_url: isLinkExisting ? existingUrl.trim() : null,
        new_sheet_title: isLinkExisting ? newSheetTitle.trim() : null,
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
      const msg = err.message || '创建任务失败';
      setCreateErrorMsg(msg);
      showError(msg);
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

      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(460px, 1.1fr) minmax(360px, 1fr)', gap: '20px', alignItems: 'stretch', marginBottom: '20px' }}>
        {/* 左侧主卡片：第 1 步与第 2 步 */}
        <div className="card workflow-primary" style={{ margin: 0, height: "100%", display: "flex", flexDirection: "column" }}>
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
                  <option value="">主账号 / 默认</option>
                  {subaccounts.map((acc) => (
                    <option key={acc.id} value={acc.id}>{acc.name} ({acc.id})</option>
                  ))}
                </select>
              </div>
            )}
          </section>

          {/* 第 2 步：上传 Excel 数据样本 */}
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
              <input
                type="file"
                id="excelFileInput"
                accept=".xlsx,.xls"
                style={{ display: 'none' }}
                onChange={handleFileChange}
              />
              <div className="upload-file-icon">X</div>
              <div className="upload-title">{file ? file.name : '点击或拖拽上传 Excel 文件'}</div>
              <div className="upload-desc">支持 .xlsx、.xls 格式，建议使用近 30 行样本数据，文件不超过 50MB</div>
            </label>
            <div className="upload-note">
              <Info className="icon" size={14} />
              <span>上传后系统将自动解析表头字段、数据类型，并自动抓取数据预览</span>
            </div>
          </section>
        </div>

        {/* 右侧卡片：未上传显示操作指引；上传后承接第 3 步与两个高级同步配置 */}
        {analyzedSheets.length === 0 ? (
          <aside className="import-rail" style={{ margin: 0 }}>
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
                    <strong>上传 Excel 样本</strong>
                    <p>使用平台导出的报表文件，系统将自动解析字段</p>
                  </div>
                </div>
                <div className="guide-item">
                  <span className="num">3</span>
                  <div>
                    <strong>核验与高级配置</strong>
                    <p>确认工作表、支持多任务合并或追加到已有表格</p>
                  </div>
                </div>
                <div className="guide-item">
                  <span className="num">4</span>
                  <div>
                    <strong>自动预览与创建</strong>
                    <p>系统自动拉取接口数据并建立飞书定时同步</p>
                  </div>
                </div>
              </div>
            </section>
          </aside>
        ) : (
          <div className="card" id="sheetAnalysisCard" style={{ margin: 0, height: "100%", display: "flex", flexDirection: "column", animation: "uiFadeUp .28s both" }}>
            <div className="card-title" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span>第三步：工作表与高级同步配置</span>
              <span style={{ fontSize: '12px', fontWeight: 'normal', color: 'var(--text-muted)' }}>
                已解析 {analyzedSheets.length} 个工作表
              </span>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', flex: 1 }}>
              {/* 1. 工作表选择区（强化徽章与结构展示） */}
              <div>
                <div style={{ fontSize: '13px', fontWeight: 600, color: '#334155', marginBottom: '8px' }}>
                  目标工作表 (Sheet)
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  {analyzedSheets.map((s, idx) => {
                    const isSelected = selectedSheetIndices.includes(idx);
                    return (
                      <div
                        key={idx}
                        className={`sheet-pill ${isSelected ? 'selected' : ''}`}
                        onClick={() => handleToggleSheet(idx)}
                        style={{
                          cursor: 'pointer',
                          padding: '12px 16px',
                          borderRadius: '8px',
                          border: isSelected ? '1.5px solid var(--primary)' : '1px solid #e2e8f0',
                          background: isSelected ? 'var(--primary-subtle)' : '#ffffff',
                          boxShadow: isSelected ? '0 2px 6px rgba(245, 63, 63, 0.08)' : 'none',
                          transition: 'all 0.18s ease',
                        }}
                      >
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <Layers size={16} style={{ color: isSelected ? 'var(--primary)' : '#64748b' }} />
                            <strong style={{ fontSize: '14px', color: isSelected ? 'var(--primary)' : '#1e293b' }}>
                              {s.sheet_title}
                            </strong>
                          </div>
                          <span style={{ fontSize: '12px', fontWeight: 600, color: isSelected ? 'var(--primary)' : '#94a3b8' }}>
                            {isSelected ? '✓ 已选中' : '未选择'}
                          </span>
                        </div>
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px', fontSize: '12px', color: '#64748b' }}>
                          <span>ID 列: <strong style={{ color: '#334155' }}>{s.id_column || '未识别'}</strong></span>
                          <span>·</span>
                          <span>日期列: <strong style={{ color: '#334155' }}>{s.date_column || '未识别'}</strong></span>
                          <span>·</span>
                          <span>识别实体: <strong style={{ color: '#334155' }}>{s.detected_entity_ids?.length || 0} 个</strong></span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* 2. 样本数据概览面板 (有效利用空间，呈现关键洞察) */}
              {analyzedSheets.length > 0 && (
                <div style={{ background: '#ffffff', border: '1px solid #e2e8f0', borderRadius: '8px', padding: '12px 14px' }}>
                  <div style={{ fontSize: '12px', fontWeight: 600, color: '#475569', marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <Hash size={14} style={{ color: 'var(--primary)' }} />
                    <span>样本数据结构分析</span>
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '8px' }}>
                    <div style={{ background: '#f8fafc', padding: '8px 10px', borderRadius: '6px', textAlign: 'center' }}>
                      <div style={{ fontSize: '11px', color: '#64748b' }}>样本历史行数</div>
                      <div style={{ fontSize: '14px', fontWeight: 700, color: '#1e293b', marginTop: '2px' }}>
                        {analyzedSheets[0]?.uploaded_rows?.length || 0} 行
                      </div>
                    </div>
                    <div style={{ background: '#f8fafc', padding: '8px 10px', borderRadius: '6px', textAlign: 'center' }}>
                      <div style={{ fontSize: '11px', color: '#64748b' }}>表头指标列数</div>
                      <div style={{ fontSize: '14px', fontWeight: 700, color: '#1e293b', marginTop: '2px' }}>
                        {analyzedSheets[0]?.headers?.length || 0} 列
                      </div>
                    </div>
                    <div style={{ background: '#f8fafc', padding: '8px 10px', borderRadius: '6px', textAlign: 'center' }}>
                      <div style={{ fontSize: '11px', color: '#64748b' }}>新数据起始日</div>
                      <div style={{ fontSize: '13px', fontWeight: 700, color: 'var(--primary)', marginTop: '3px' }}>
                        {analyzedSheets[0]?.next_start_date ? analyzedSheets[0].next_start_date.slice(5) : '最新'}
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* 3. 高级扩展选项卡片 (结构饱满精致，强化视觉层次) */}
              <div style={{ border: '1px solid #e2e8f0', borderRadius: '8px', padding: '14px', background: '#f8fafc', display: 'flex', flexDirection: 'column', gap: '14px', flex: 1 }}>
                <div style={{ fontSize: '13px', fontWeight: 600, color: '#1e293b', borderBottom: '1px solid #e2e8f0', paddingBottom: '8px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <span>⚙️ 同步模式与目标扩展配置</span>
                </div>

                {/* 选项 1：多任务合并 */}
                <div style={{ background: '#ffffff', border: '1px solid #e2e8f0', borderRadius: '8px', padding: '12px' }}>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '10px', cursor: 'pointer', fontWeight: 600, fontSize: '13px', color: '#1e293b' }}>
                    <input
                      type="checkbox"
                      checked={isMergeTasks}
                      onChange={(e) => {
                        setIsMergeTasks(e.target.checked);
                        if (e.target.checked && !customTaskIdsInput) {
                          const defaultIds = analyzedSheets[selectedSheetIndices[0] || 0]?.detected_entity_ids || [];
                          setCustomTaskIdsInput(defaultIds.join(', '));
                        }
                        setTimeout(() => previewMutation.mutate(), 80);
                      }}
                      style={{ width: '16px', height: '16px', accentColor: '#f53f3f', cursor: 'pointer' }}
                    />
                    <span>⚡ 开启多任务合并为一个 Sheet</span>
                  </label>
                  {isMergeTasks ? (
                    <div style={{ marginTop: '10px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                      <span style={{ fontSize: '12px', color: '#64748b' }}>
                        输入要合并的任务 ID（多个请使用英文逗号或空格分隔）：
                      </span>
                      <input
                        type="text"
                        className="form-control"
                        placeholder="例如: 204611, 210427"
                        value={customTaskIdsInput}
                        onChange={(e) => setCustomTaskIdsInput(e.target.value)}
                        onBlur={() => previewMutation.mutate()}
                        style={{ width: '100%', fontSize: '13px', height: '36px' }}
                      />
                      <div style={{ fontSize: '11px', color: '#64748b', background: '#f8fafc', padding: '6px 10px', borderRadius: '4px', borderLeft: '3px solid #165dff', lineHeight: '1.5' }}>
                        💡 若新任务包含当前表头未覆盖的列，系统将在飞书工作表右侧自动动态追加新列，其余任务留空，杜绝错位。
                      </div>
                    </div>
                  ) : (
                    <div style={{ fontSize: '11px', color: '#94a3b8', marginTop: '6px', paddingLeft: '26px' }}>
                      默认按样本中提取的单一实体进行同步；勾选后可自由追加多个任务 ID 统一汇总。
                    </div>
                  )}
                </div>

                {/* 选项 2：链接到已有飞书表格 */}
                <div style={{ background: '#ffffff', border: '1px solid #e2e8f0', borderRadius: '8px', padding: '12px' }}>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '10px', cursor: 'pointer', fontWeight: 600, fontSize: '13px', color: '#1e293b' }}>
                    <input
                      type="checkbox"
                      checked={isLinkExisting}
                      onChange={(e) => {
                        setIsLinkExisting(e.target.checked);
                        if (e.target.checked && !newSheetTitle) {
                          setNewSheetTitle(taskName || '数据同步');
                        }
                      }}
                      style={{ width: '16px', height: '16px', accentColor: '#f53f3f', cursor: 'pointer' }}
                    />
                    <span>🔗 链接到已有飞书表格（在已有文档末尾新增 Sheet）</span>
                  </label>

                  {isLinkExisting ? (
                    <div style={{ marginTop: '12px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
                      <div>
                        <span style={{ fontSize: '12px', fontWeight: 500, color: '#475569', display: 'block', marginBottom: '4px' }}>
                          已有表格链接（支持普通表格或知识库 Wiki 链接）*
                        </span>
                        <input
                          type="text"
                          className="form-control"
                          placeholder="https://yimeichuanbo.feishu.cn/wiki/... 或 /sheets/..."
                          value={existingUrl}
                          onChange={(e) => setExistingUrl(e.target.value)}
                          style={{ width: '100%', fontSize: '13px', height: '36px' }}
                        />
                      </div>
                      <div>
                        <span style={{ fontSize: '12px', fontWeight: 500, color: '#475569', display: 'block', marginBottom: '4px' }}>
                          新增子表 (Sheet) 名称*
                        </span>
                        <input
                          type="text"
                          className="form-control"
                          placeholder="输入要在该文档中新建的 Sheet 标题"
                          value={newSheetTitle}
                          onChange={(e) => setNewSheetTitle(e.target.value)}
                          style={{ width: '100%', fontSize: '13px', height: '36px' }}
                        />
                      </div>
                      {/* 权限提醒指引 */}
                      <div style={{ background: '#fffbe6', border: '1px solid #ffe58f', borderRadius: '6px', padding: '9px 12px', fontSize: '12px', color: '#d46b08', lineHeight: '1.5' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <strong>⚠️ 必须先在表格中添加「信息流自动」文档应用并设为「可编辑」</strong>
                          <button
                            type="button"
                            onClick={() => setShowInstruction(!showInstruction)}
                            style={{ background: 'none', border: 'none', color: '#165dff', cursor: 'pointer', fontSize: '12px', padding: 0 }}
                          >
                            {showInstruction ? '收起步骤 ▲' : '查看步骤 ▼'}
                          </button>
                        </div>
                        {showInstruction && (
                          <ol style={{ margin: '8px 0 0 16px', padding: 0, color: '#595959' }}>
                            <li>打开目标表格，点击右上角 <strong>「···」</strong>；</li>
                            <li>点击 <strong>「添加文档应用」</strong> 并搜索 <strong>「信息流自动」</strong>；</li>
                            <li>权限务必选为 <strong>「可编辑」</strong>，点击确认添加；</li>
                            <li>添加完成后方可在此点击创建任务，自动追加 Sheet 同步。</li>
                          </ol>
                        )}
                      </div>
                    </div>
                  ) : (
                    <div style={{ fontSize: '11px', color: '#94a3b8', marginTop: '6px', paddingLeft: '26px' }}>
                      默认在飞书个人空间下自动创建新在线表格；勾选后可无缝挂载至已有团队文档。
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>        )}
      </div>

      {/* 第 4 步：调取平台接口数据预览 (全宽大表格视图) */}
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
              {previewMutation.isPending ? '抓取中…' : '🔄 重新测试抓取'}
            </button>
          </div>

          {previewMutation.isPending ? (
            <div style={{ padding: '36px', textAlign: 'center', color: '#64748b', fontSize: '13px' }}>
              ⏳ 正在自动调用目标平台接口抓取最新数据并校验字段映射，请稍候…
            </div>
          ) : previewMutation.data ? (
            <div className="table-container" style={{ maxHeight: '320px', overflowY: 'auto' }}>
              <table>
                <thead>
                  <tr>
                    {previewMutation.data.headers.map((h: string, i: number) => (
                      <th key={i}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {previewMutation.data.rows.slice(0, 15).map((row: any[], rIdx: number) => (
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
            <div className="empty-prompt">
              <RotateCw size={24} style={{ animation: 'spin 1.5s linear infinite' }} />
              <span>正在自动调取目标平台数据并核验字段映射…</span>
            </div>
          )}
        </div>
      )}

      {/* 第 5 步：创建任务与定时配置 (全宽) */}
      {analyzedSheets.length > 0 && (
        <div className="card" id="scheduleConfigCard" style={{ animation: 'uiFadeUp .28s both' }}>
          <div className="card-title">第五步：创建飞书表格并配置定时自动同步</div>

          <div className="form-row">
            <div className="form-group" style={{ flex: 2 }}>
              <label>任务名称</label>
              <input
                type="text"
                className="form-control"
                value={taskName}
                onChange={(e) => {
                  setTaskName(e.target.value);
                  setCreateErrorMsg('');
                }}
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
          </div>

          <div style={{ border: '1px solid var(--border)', borderRadius: '8px', padding: '18px', background: '#fafbfc', margin: '16px 0' }}>
            <SchedulePicker
              label="⏰ 自动化同步周期 (RRULE)"
              value={rrule}
              onChange={setRrule}
            />
          </div>

          {/* 醒目的错误警示卡片（当接口报错或缺少机器人权限时直接在此展示） */}
          {createErrorMsg && (
            <div
              style={{
                margin: '12px 0',
                padding: '12px 16px',
                background: '#fff2f0',
                border: '1px solid #ffccc7',
                borderRadius: '8px',
                color: '#cf1322',
                fontSize: '13px',
                lineHeight: '1.6',
              }}
            >
              <strong style={{ display: 'block', marginBottom: '4px' }}>❌ 创建任务未成功：</strong>
              <div>{createErrorMsg}</div>
            </div>
          )}

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px', marginTop: '12px' }}>
            <button
              type="button"
              className="btn btn-primary"
              disabled={createTaskMutation.isPending || !taskName.trim() || selectedSheetIndices.length === 0 || (isLinkExisting && (!existingUrl.trim() || !newSheetTitle.trim()))}
              onClick={() => {
                setCreateErrorMsg('');
                createTaskMutation.mutate();
              }}
            >
              {createTaskMutation.isPending ? '创建中…' : '🚀 立即生成飞书表格并启用定时任务'}
            </button>
          </div>
        </div>
      )}
    </>
  );
};
