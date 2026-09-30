import React, { useState } from 'react';
import { NavLink, Outlet, useLocation } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  FileSpreadsheet,
  Upload,
  ListTodo,
  History,
  Search,
  Settings,
  ShieldCheck,
  ShieldAlert,
  LogOut,
  ExternalLink,
  Lock
} from 'lucide-react';
import { fetchJson } from '@/shared/api/client';
import { Dialog } from '@/shared/components/Dialog';
import { Button } from '@/shared/components/Button';
import { useToast } from '@/shared/components/Toast';

export const AppShell: React.FC = () => {
  const location = useLocation();
  const queryClient = useQueryClient();
  const { showSuccess, showError } = useToast();
  const [loginModalOpen, setLoginModalOpen] = useState(false);
  const [password, setPassword] = useState('');

  // 检查管理员登录状态
  const { data: authData } = useQuery({
    queryKey: ['authCheck'],
    queryFn: () => fetchJson<{ authenticated: boolean }>('/api/auth/check'),
  });
  const isAuthenticated = authData?.authenticated ?? false;

  const loginMutation = useMutation({
    mutationFn: (pwd: string) =>
      fetchJson<{ success: boolean }>('/api/auth/login', {
        method: 'POST',
        body: JSON.stringify({ password: pwd }),
      }),
    onSuccess: () => {
      showSuccess('管理员口令验证通过');
      setLoginModalOpen(false);
      setPassword('');
      queryClient.invalidateQueries({ queryKey: ['authCheck'] });
      queryClient.invalidateQueries({ queryKey: ['settings'] });
    },
    onError: (err: any) => {
      showError(err.message || '口令错误');
    },
  });

  const logoutMutation = useMutation({
    mutationFn: () => fetchJson<{ success: boolean }>('/api/auth/logout', { method: 'POST' }),
    onSuccess: () => {
      showSuccess('已安全退出管理模式');
      queryClient.invalidateQueries({ queryKey: ['authCheck'] });
    },
  });

  const isSyncSection = ['/', '/import', '/tasks', '/runs'].includes(location.pathname);
  const isKeywordSection = location.pathname.startsWith('/keyword');

  const navItemStyle = (isActive: boolean): React.CSSProperties => ({
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
    padding: '9px 14px',
    borderRadius: '8px',
    fontSize: '14px',
    fontWeight: isActive ? 600 : 500,
    color: isActive ? '#ea3445' : '#475569',
    backgroundColor: isActive ? '#fef2f2' : 'transparent',
    textDecoration: 'none',
    transition: 'all 0.15s ease',
  });

  return (
    <div style={{ display: 'flex', minHeight: '100vh', backgroundColor: '#f8fafc' }}>
      {/* 侧边导航栏 */}
      <aside
        style={{
          width: '240px',
          backgroundColor: '#ffffff',
          borderRight: '1px solid #e2e8f0',
          display: 'flex',
          flexDirection: 'column',
          position: 'fixed',
          top: 0,
          bottom: 0,
          left: 0,
          zIndex: 100,
        }}
      >
        {/* 产品 Header */}
        <div
          style={{
            padding: '20px 18px',
            borderBottom: '1px solid #f1f5f9',
            display: 'flex',
            alignItems: 'center',
            gap: '10px',
          }}
        >
          <div
            style={{
              width: '34px',
              height: '34px',
              borderRadius: '8px',
              backgroundColor: '#ea3445',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#ffffff',
            }}
          >
            <FileSpreadsheet size={20} />
          </div>
          <div>
            <h1 style={{ fontSize: '15px', fontWeight: 700, color: '#0f172a', lineHeight: 1.2 }}>
              飞书同步中心
            </h1>
            <span style={{ fontSize: '11px', color: '#94a3b8' }}>三平台 & 关键词看板</span>
          </div>
        </div>

        {/* 菜单列表 */}
        <div style={{ flex: 1, padding: '16px 12px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '20px' }}>
          {/* 数据同步板块 */}
          <div>
            <div style={{ fontSize: '11px', fontWeight: 600, color: '#94a3b8', padding: '0 8px 8px', letterSpacing: '0.05em' }}>
              数据自动同步
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
              <NavLink to="/import" style={({ isActive }) => navItemStyle(isActive)}>
                <Upload size={17} /> 导入新表
              </NavLink>
              <NavLink to="/tasks" style={({ isActive }) => navItemStyle(isActive)}>
                <ListTodo size={17} /> 同步任务
              </NavLink>
              <NavLink to="/runs" style={({ isActive }) => navItemStyle(isActive)}>
                <History size={17} /> 运行记录
              </NavLink>
            </div>
          </div>

          {/* 关键词板块 */}
          <div>
            <div style={{ fontSize: '11px', fontWeight: 600, color: '#94a3b8', padding: '0 8px 8px', letterSpacing: '0.05em' }}>
              关键词监控
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
              <NavLink to="/keyword" end style={({ isActive }) => navItemStyle(isActive)}>
                <Search size={17} /> 关键词洞察
              </NavLink>
              <NavLink to="/keyword/tasks" style={({ isActive }) => navItemStyle(isActive)}>
                <ListTodo size={17} /> 关键词任务
              </NavLink>
              <NavLink to="/keyword/runs" style={({ isActive }) => navItemStyle(isActive)}>
                <History size={17} /> 运行记录
              </NavLink>
            </div>
          </div>

          {/* 系统板块 */}
          <div>
            <div style={{ fontSize: '11px', fontWeight: 600, color: '#94a3b8', padding: '0 8px 8px', letterSpacing: '0.05em' }}>
              系统配置
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
              <NavLink to="/settings" style={({ isActive }) => navItemStyle(isActive)}>
                <Settings size={17} /> 系统设置
              </NavLink>
            </div>
          </div>
        </div>

        {/* 底部鉴权控制卡片 */}
        <div style={{ padding: '14px', borderTop: '1px solid #f1f5f9', backgroundColor: '#fcfcfd' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              {isAuthenticated ? (
                <>
                  <ShieldCheck size={18} color="#16a34a" />
                  <span style={{ fontSize: '12px', fontWeight: 600, color: '#16a34a' }}>管理员已授权</span>
                </>
              ) : (
                <>
                  <ShieldAlert size={18} color="#94a3b8" />
                  <span style={{ fontSize: '12px', color: '#64748b' }}>访客只读模式</span>
                </>
              )}
            </div>
            {isAuthenticated ? (
              <button
                onClick={() => logoutMutation.mutate()}
                title="退出管理权限"
                style={{
                  background: 'none',
                  border: 'none',
                  cursor: 'pointer',
                  color: '#94a3b8',
                  padding: '4px',
                  display: 'flex',
                }}
              >
                <LogOut size={16} />
              </button>
            ) : (
              <Button size="sm" variant="secondary" onClick={() => setLoginModalOpen(true)}>
                <Lock size={13} /> 登录
              </Button>
            )}
          </div>
        </div>
      </aside>

      {/* 主展示区 */}
      <main style={{ flex: 1, marginLeft: '240px', minHeight: '100vh', padding: '24px 32px' }}>
        <Outlet />
      </main>

      {/* 管理员登录弹窗 */}
      <Dialog isOpen={loginModalOpen} onClose={() => setLoginModalOpen(false)} title="管理员口令验证" width="400px">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (password) loginMutation.mutate(password);
          }}
          style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}
        >
          <div style={{ fontSize: '13px', color: '#64748b' }}>
            请输入系统管理员访问口令以获得修改设置、创建任务及执行同步操作权限：
          </div>
          <input
            type="password"
            autoFocus
            placeholder="请输入 ACCESS_TOKEN"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            style={{
              padding: '10px 12px',
              border: '1px solid #cbd5e1',
              borderRadius: '6px',
              outline: 'none',
              fontSize: '14px',
            }}
          />
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
            <Button variant="secondary" type="button" onClick={() => setLoginModalOpen(false)}>
              取消
            </Button>
            <Button variant="primary" type="submit" loading={loginMutation.isPending}>
              验证登录
            </Button>
          </div>
        </form>
      </Dialog>
    </div>
  );
};

