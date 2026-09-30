import React, { useState } from 'react';
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  PlusCircle,
  ClipboardList,
  Clock3,
  BarChart3,
  LayoutDashboard,
  Search,
  CircleHelp,
  Sparkles,
  X
} from 'lucide-react';
import { fetchJson } from '@/shared/api/client';

export const AppShell: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const [helpDrawerOpen, setHelpDrawerOpen] = useState(false);

  const isKeywordSection = location.pathname.startsWith('/keyword');
  const isLingxiSection = location.pathname.startsWith('/lingxi');

  // 获取同步任务数量徽标
  const { data: syncTasks = [] } = useQuery<any[]>({
    queryKey: ['syncTasks'],
    queryFn: () => fetchJson('/api/tasks'),
  });

  // 获取关键词任务数量徽标
  const { data: keywordTasks = [] } = useQuery<any[]>({
    queryKey: ['keywordTasks'],
    queryFn: () => fetchJson('/api/keyword/tasks'),
  });

  // 获取灵犀任务数量徽标
  const { data: lingxiTasks = [] } = useQuery<any[]>({
    queryKey: ['lingxiTasks'],
    queryFn: () => fetchJson('/api/lingxi/tasks'),
  });

  return (
    <>
      {/* 顶部导航栏 (完全还原原版样式) */}
      <div className="header">
        <div className="brand">
          <span className="brand-mark">AD</span>
          <h1>广告数据自动同步中心</h1>
        </div>
      </div>

      {/* 原版左侧导航栏 */}
      <aside className="sidebar" aria-label="主导航">
        {isLingxiSection ? (
          /* 灵犀关键词 导航组 */
          <div id="sidebar-group-lingxi" className="sidebar-nav">
            <button
              className="sidebar-link"
              type="button"
              onClick={() => navigate('/import')}
            >
              <LayoutDashboard className="icon" size={16} />
              <span className="nav-label">数据同步中心</span>
            </button>
            <button
              className="sidebar-link"
              type="button"
              onClick={() => navigate('/keyword')}
            >
              <BarChart3 className="icon" size={16} />
              <span className="nav-label">聚光关键词</span>
            </button>
            <div className="sidebar-divider" />
            <NavLink
              to="/lingxi"
              end
              className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}
            >
              <Search className="icon" size={16} />
              <span className="nav-label">查询与概览</span>
            </NavLink>
            <NavLink
              to="/lingxi/tasks"
              className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}
            >
              <ClipboardList className="icon" size={16} />
              <span className="nav-label">同步任务列表</span>
              <span id="lingxiTaskCountBadge" className="badge badge-gray" style={{ marginLeft: 'auto' }}>
                {lingxiTasks.length}
              </span>
            </NavLink>
            <NavLink
              to="/lingxi/runs"
              className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}
            >
              <Clock3 className="icon" size={16} />
              <span className="nav-label">运行记录</span>
            </NavLink>
          </div>
        ) : isKeywordSection ? (
            /* 聚光关键词 导航组 (顺序固定：数据同步中心 -> 聚光关键词子导航 -> 灵犀关键词) */
            <div id="sidebar-group-keyword" className="sidebar-nav">
              <button
                className="sidebar-link"
                type="button"
                onClick={() => navigate('/import')}
              >
                <LayoutDashboard className="icon" size={16} />
                <span className="nav-label">数据同步中心</span>
              </button>
              <div className="sidebar-divider" />
            <NavLink
              to="/keyword"
              end
              className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}
            >
              <Search className="icon" size={16} />
              <span className="nav-label">查询与概览</span>
            </NavLink>
            <NavLink
              to="/keyword/tasks"
              className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}
            >
              <ClipboardList className="icon" size={16} />
              <span className="nav-label">同步任务列表</span>
              <span id="kwTaskCountBadge" className="badge badge-gray" style={{ marginLeft: 'auto' }}>
                {keywordTasks.length}
              </span>
            </NavLink>
              <NavLink
                to="/keyword/runs"
                className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}
              >
                <Clock3 className="icon" size={16} />
                <span className="nav-label">运行记录</span>
              </NavLink>
              <div className="sidebar-divider" />
              <button
                className="sidebar-link"
                type="button"
                onClick={() => navigate('/lingxi')}
              >
                <Sparkles className="icon" size={16} />
                <span className="nav-label">灵犀关键词</span>
              </button>
            </div>
        ) : (
          /* 数据同步中心 导航组 */
          <div id="sidebar-group-sync" className="sidebar-nav">
            <NavLink
              to="/import"
              className={({ isActive }) => `nav-tab ${isActive ? 'active' : ''}`}
            >
              <PlusCircle className="icon" size={16} />
              <span className="nav-label">新建同步任务</span>
            </NavLink>
            <NavLink
              to="/tasks"
              className={({ isActive }) => `nav-tab ${isActive ? 'active' : ''}`}
            >
              <ClipboardList className="icon" size={16} />
              <span className="nav-label">同步任务</span>
              <span id="taskCountBadge" className="badge badge-gray" style={{ marginLeft: 'auto' }}>
                {syncTasks.length}
              </span>
            </NavLink>
            <NavLink
              to="/runs"
              className={({ isActive }) => `nav-tab ${isActive ? 'active' : ''}`}
            >
              <Clock3 className="icon" size={16} />
              <span className="nav-label">运行记录</span>
            </NavLink>
            <div className="sidebar-divider" />
            <button
              className="sidebar-link"
              type="button"
              onClick={() => navigate('/keyword')}
            >
              <BarChart3 className="icon" size={16} />
              <span className="nav-label">聚光关键词</span>
            </button>
            <button
              className="sidebar-link"
              type="button"
              onClick={() => navigate('/lingxi')}
            >
              <Sparkles className="icon" size={16} />
              <span className="nav-label">灵犀关键词</span>
            </button>
          </div>
        )}

        <div className="sidebar-spacer" />
        <button
          className="sidebar-link muted"
          type="button"
          onClick={() => setHelpDrawerOpen(true)}
        >
          <CircleHelp className="icon" size={16} />
          <span className="nav-label">使用帮助</span>
        </button>
      </aside>

      {/* 主展示区 */}
      <div className="container">
        <Outlet />
      </div>

      {/* 原版使用帮助 Drawer */}
      <div
        className="help-backdrop"
        style={{ display: helpDrawerOpen ? 'block' : 'none' }}
        onClick={(e) => {
          if (e.target === e.currentTarget) setHelpDrawerOpen(false);
        }}
      >
        <aside className="help-drawer" role="dialog" aria-modal="true">
          <div className="help-head">
            <h2>使用帮助</h2>
            <button className="help-close" type="button" onClick={() => setHelpDrawerOpen(false)}>
              <X size={18} />
            </button>
          </div>
          <div className="help-body">
            <div className="help-intro">
              按照常规步骤完成广告数据自动同步。若遇异常可查看运行记录获取详细日志。
            </div>
            <div className="guide-list" style={{ marginTop: '16px' }}>
              <div className="guide-item">
                <span className="num">1</span>
                <div>
                  <strong>选择投放平台</strong>
                  <p>支持京准通、淘宝星河、小红书聚光</p>
                </div>
              </div>
              <div className="guide-item">
                <span className="num">2</span>
                <div>
                  <strong>上传 Excel 数据样本</strong>
                  <p>自动识别表头字段并匹配实体 ID</p>
                </div>
              </div>
              <div className="guide-item">
                <span className="num">3</span>
                <div>
                  <strong>核验数据与定时调度</strong>
                  <p>配置同步周期并自动生成飞书报表</p>
                </div>
              </div>
            </div>
          </div>
        </aside>
      </div>
    </>
  );
};

