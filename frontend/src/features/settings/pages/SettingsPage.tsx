import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Settings, FolderCheck, Bell, Key, RefreshCw, CheckCircle2, ShieldCheck, Lock } from 'lucide-react';
import { fetchJson } from '@/shared/api/client';
import { Button } from '@/shared/components/Button';
import { useToast } from '@/shared/components/Toast';

export const SettingsPage: React.FC = () => {
  const queryClient = useQueryClient();
  const { showSuccess, showError } = useToast();

  const [cookieInput, setCookieInput] = useState('');
  const [sellerIdInput, setSellerIdInput] = useState('');
  const [showCookie, setShowCookie] = useState(false);

  // 获取设置信息 (需要管理员)
  const { data: settings, isLoading: settingsLoading, refetch: refetchSettings } = useQuery<{
    shared_folder_token: string;
    shared_folder_name: string;
    feishu_chat_id: string;
    notification_webhook: string;
    notification_policy: string;
  }>({
    queryKey: ['settings'],
    queryFn: () => fetchJson('/api/settings'),
    retry: false,
  });

  // 获取 Cookie 状态 (仅返回 configured 与 seller_id，绝不暴露明文)
  const { data: cookieInfo, refetch: refetchCookie } = useQuery<{
    configured: boolean;
    v_seller_id: string;
    cookie_length: number;
  }>({
    queryKey: ['cookieStatus'],
    queryFn: () => fetchJson('/api/keyword/cookie'),
    retry: false,
  });

  // 创建告警群
  const createChatMutation = useMutation({
    mutationFn: () =>
      fetchJson<{ chat_id: string }>('/api/feishu/create_chat', {
        method: 'POST',
        body: JSON.stringify({ name: '数据同步告警群' }),
      }),
    onSuccess: (res) => {
      showSuccess(`成功创建飞书告警群 (ChatID: ${res.chat_id})`);
      refetchSettings();
    },
    onError: (err: any) => {
      showError(err.message || '创建告警群失败');
    },
  });

  // 更新 Cookie
  const updateCookieMutation = useMutation({
    mutationFn: () =>
      fetchJson<{ success: boolean; message: string }>('/api/keyword/cookie', {
        method: 'POST',
        body: JSON.stringify({ cookie: cookieInput, v_seller_id: sellerIdInput }),
      }),
    onSuccess: (res) => {
      showSuccess(res.message || '小红书聚光 Cookie 更新成功！已自动生效。');
      setCookieInput('');
      refetchCookie();
    },
    onError: (err: any) => {
      showError(err.message || '更新 Cookie 失败');
    },
  });

  return (
    <div style={{ maxWidth: '900px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '24px' }}>
      <div>
        <h2 style={{ fontSize: '20px', fontWeight: 700, color: '#0f172a' }}>系统集成配置</h2>
        <p style={{ fontSize: '13px', color: '#64748b', marginTop: '4px' }}>
          查看飞书共享云盘、通知群及小红书聚光数据源凭据配置状态
        </p>
      </div>

      {/* 飞书共享云盘 */}
      <div style={{ backgroundColor: '#ffffff', borderRadius: '12px', padding: '20px', border: '1px solid #e2e8f0', display: 'flex', flexDirection: 'column', gap: '16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <FolderCheck size={20} color="#ea3445" />
          <h3 style={{ fontSize: '15px', fontWeight: 600, color: '#0f172a' }}>飞书云文档与共享空间</h3>
        </div>
        <div style={{ fontSize: '13px', color: '#475569', display: 'flex', flexDirection: 'column', gap: '8px' }}>
          <div>
            共享文件夹名称：<strong>{settings?.shared_folder_name || '数据自动同步表'}</strong>
          </div>
          <div>
            文件夹 Token：
            <code style={{ padding: '2px 6px', backgroundColor: '#f1f5f9', borderRadius: '4px', fontSize: '12px' }}>
              {settings?.shared_folder_token || '自动建立在飞书根目录'}
            </code>
          </div>
        </div>
      </div>

      {/* 飞书告警群组 */}
      <div style={{ backgroundColor: '#ffffff', borderRadius: '12px', padding: '20px', border: '1px solid #e2e8f0', display: 'flex', flexDirection: 'column', gap: '16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <Bell size={20} color="#ea3445" />
            <h3 style={{ fontSize: '15px', fontWeight: 600, color: '#0f172a' }}>飞书告警与通知群组</h3>
          </div>
          <Button
            size="sm"
            variant="secondary"
            loading={createChatMutation.isPending}
            onClick={() => createChatMutation.mutate()}
          >
            一键创建告警群
          </Button>
        </div>
        <div style={{ fontSize: '13px', color: '#475569' }}>
          {settings?.feishu_chat_id ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#16a34a' }}>
              <CheckCircle2 size={16} /> 已绑定告警群 ID: {settings.feishu_chat_id}
            </div>
          ) : (
            <div style={{ color: '#64748b' }}>未配置告警群 ID，可通过右侧按钮快速自动创建通知群。</div>
          )}
        </div>
      </div>

      {/* 小红书聚光凭据配置 */}
      <div style={{ backgroundColor: '#ffffff', borderRadius: '12px', padding: '20px', border: '1px solid #e2e8f0', display: 'flex', flexDirection: 'column', gap: '16px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <Key size={20} color="#ea3445" />
          <h3 style={{ fontSize: '15px', fontWeight: 600, color: '#0f172a' }}>小红书聚光 API 凭据配置</h3>
        </div>

        <div style={{ padding: '12px 16px', backgroundColor: '#f8fafc', borderRadius: '8px', fontSize: '13px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div>
              当前凭据状态：
              {cookieInfo?.configured ? (
                <span style={{ color: '#16a34a', fontWeight: 600, marginLeft: '6px' }}>
                  已配置有效 (商家ID: {cookieInfo.v_seller_id})
                </span>
              ) : (
                <span style={{ color: '#dc2626', fontWeight: 600, marginLeft: '6px' }}>未配置或已失效</span>
              )}
            </div>
            <Button size="sm" variant="ghost" onClick={() => refetchCookie()}>
              <RefreshCw size={13} /> 检查状态
            </Button>
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          <div>
            <label style={{ fontSize: '13px', fontWeight: 600, color: '#334155', display: 'block', marginBottom: '6px' }}>
              商家 vSellerId
            </label>
            <input
              type="text"
              value={sellerIdInput}
              onChange={(e) => setSellerIdInput(e.target.value)}
              style={{
                width: '100%',
                padding: '8px 12px',
                borderRadius: '6px',
                border: '1px solid #cbd5e1',
                fontSize: '14px',
              }}
            />
          </div>

          <div>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '6px' }}>
              <label style={{ fontSize: '13px', fontWeight: 600, color: '#334155' }}>
                更新聚光 Cookie
              </label>
              <button
                type="button"
                onClick={() => setShowCookie(!showCookie)}
                style={{
                  background: 'none',
                  border: 'none',
                  color: '#2563eb',
                  fontSize: '12px',
                  cursor: 'pointer',
                  padding: '2px 4px'
                }}
              >
                {showCookie ? '隐藏凭据' : '显示明文'}
              </button>
            </div>
            <input
              type={showCookie ? 'text' : 'password'}
              placeholder="从浏览器复制包含 a1= 的有效聚光 Cookie 粘贴至此更新"
              value={cookieInput}
              onChange={(e) => setCookieInput(e.target.value)}
              style={{
                width: '100%',
                padding: '8px 12px',
                borderRadius: '6px',
                border: '1px solid #cbd5e1',
                fontSize: '13px',
                fontFamily: 'monospace',
              }}
            />
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
            <Button
              variant="primary"
              loading={updateCookieMutation.isPending}
              disabled={!cookieInput.trim()}
              onClick={() => updateCookieMutation.mutate()}
            >
              更新并立即生效
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
};

