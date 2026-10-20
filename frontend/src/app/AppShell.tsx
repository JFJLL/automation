import React, { useState, useEffect } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  PlusCircle,
  ClipboardList,
  Clock3,
  BarChart3,
  LayoutDashboard,
  Search,
  CircleHelp,
  Sparkles,
  Lock,
  LogOut,
  X,
  ShieldCheck,
  Trash2,
  ArchiveRestore
} from "lucide-react";
import { fetchJson } from "@/shared/api/client";
import { SimplePromoGatekeeper } from "@/features/simple_promo/components/SimplePromoGatekeeper";

export const AppShell: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const [helpDrawerOpen, setHelpDrawerOpen] = useState(false);

  const isKeywordSection = location.pathname.startsWith("/keyword");
  const isLingxiSection = location.pathname.startsWith("/lingxi");
  const isAdminSection = location.pathname.startsWith("/admin") || location.pathname.startsWith("/simple-promo");
  const isSimplePromoSection =
    location.pathname.startsWith("/admin/promo") ||
    location.pathname.startsWith("/simple-promo");

  // 简单投私密板块口令解锁状态 (保存在 sessionStorage，刷新或重开重置)
  const [isPromoUnlocked, setIsPromoUnlocked] = useState<boolean>(() => {
    return Boolean(sessionStorage.getItem("simple_promo_token"));
  });

  const handleLockPromo = () => {
    sessionStorage.removeItem("simple_promo_token");
    setIsPromoUnlocked(false);
  };

  // 获取同步任务列表 (5分钟 staleTime 避免高频重复拉取)
  const { data: syncTasks = [] } = useQuery<any[]>({
    queryKey: ["syncTasks"],
    queryFn: () => fetchJson("/api/tasks"),
    staleTime: 5 * 60 * 1000,
  });

  // 获取关键词任务列表
  const { data: keywordTasks = [] } = useQuery<any[]>({
    queryKey: ["keywordTasks"],
    queryFn: () => fetchJson("/api/keyword/tasks"),
    staleTime: 5 * 60 * 1000,
  });

  // 获取灵犀任务列表
  const { data: lingxiTasks = [] } = useQuery<any[]>({
    queryKey: ["lingxiTasks"],
    queryFn: () => fetchJson("/api/lingxi/tasks"),
    staleTime: 5 * 60 * 1000,
  });

  // 获取简单投任务列表 (仅在进入简单投且口令解锁时才查询，避免无关请求开销)
  const { data: simplePromoTasks = [] } = useQuery<any[]>({
    queryKey: ["simplePromoTasks"],
    queryFn: () => fetchJson("/api/simple-promo/tasks"),
    enabled: isSimplePromoSection && isPromoUnlocked,
    staleTime: 5 * 60 * 1000,
  });

  return (
    <>
      {/* 顶部导航 */}
      <div className="header">
        <div className="brand">
          <span className="brand-mark">AD</span>
          <h1>投放数据自动同步中心</h1>
        </div>
      </div>

      {/* 侧边导航 */}
      <aside className="sidebar" aria-label="侧边栏">
        {isAdminSection ? (
          /* 管理工作台 私密导航组 (仅在输入路径并解锁后展现) */
          <div id="sidebar-group-admin" className="sidebar-nav">
            <button
              className="sidebar-link"
              type="button"
              onClick={() => navigate("/import")}
            >
              <LayoutDashboard className="icon" size={16} />
              <span className="nav-label">数据同步中心</span>
            </button>
            <button
              className="sidebar-link"
              type="button"
              onClick={() => navigate("/keyword")}
            >
              <BarChart3 className="icon" size={16} />
              <span className="nav-label">聚光关键词</span>
            </button>
            <button
              className="sidebar-link"
              type="button"
              onClick={() => navigate("/lingxi")}
            >
              <Sparkles className="icon" size={16} />
              <span className="nav-label">灵犀关键词</span>
            </button>
            {isPromoUnlocked && (
              <>
                <div className="sidebar-divider" />
                <NavLink
                  to="/admin"
                  end
                  className={({ isActive }) => `sidebar-link ${isActive ? "active" : ""}`}
                >
                  <ShieldCheck className="icon" size={16} />
                  <span className="nav-label">管理总览</span>
                </NavLink>
                <NavLink
                  to="/admin/tasks"
                  className={({ isActive }) => `sidebar-link ${isActive ? "active" : ""}`}
                >
                  <Trash2 className="icon" size={16} />
                  <span className="nav-label">任务归档删除</span>
                </NavLink>
                <NavLink
                  to="/admin/audit"
                  className={({ isActive }) => `sidebar-link ${isActive ? "active" : ""}`}
                >
                  <ArchiveRestore className="icon" size={16} />
                  <span className="nav-label">删除归档记录</span>
                </NavLink>
                <NavLink
                  to="/admin/promo"
                  end
                  className={({ isActive }) => `sidebar-link ${isActive ? "active" : ""}`}
                >
                  <Search className="icon" size={16} />
                  <span className="nav-label">巡检工作台</span>
                </NavLink>
                <NavLink
                  to="/admin/promo/tasks"
                  className={({ isActive }) => `sidebar-link ${isActive ? "active" : ""}`}
                >
                  <ClipboardList className="icon" size={16} />
                  <span className="nav-label">定时巡检任务</span>
                  <span id="promoTaskCountBadge" className="badge badge-gray" style={{ marginLeft: "auto" }}>
                    {simplePromoTasks.length}
                  </span>
                </NavLink>
                <NavLink
                  to="/admin/promo/runs"
                  className={({ isActive }) => `sidebar-link ${isActive ? "active" : ""}`}
                >
                  <Clock3 className="icon" size={16} />
                  <span className="nav-label">运行记录与恢复</span>
                </NavLink>
                <div className="sidebar-divider" />
                <button
                  className="sidebar-link muted"
                  type="button"
                  onClick={handleLockPromo}
                  title="锁定并清除当前解锁会话"
                >
                  <LogOut className="icon" size={15} />
                  <span className="nav-label">重新锁定退出</span>
                </button>
              </>
            )}
          </div>
        ) : isLingxiSection ? (
          /* 灵犀关键词 导航组 */
          <div id="sidebar-group-lingxi" className="sidebar-nav">
            <button
              className="sidebar-link"
              type="button"
              onClick={() => navigate("/import")}
            >
              <LayoutDashboard className="icon" size={16} />
              <span className="nav-label">数据同步中心</span>
            </button>
            <button
              className="sidebar-link"
              type="button"
              onClick={() => navigate("/keyword")}
            >
              <BarChart3 className="icon" size={16} />
              <span className="nav-label">聚光关键词</span>
            </button>
            <div className="sidebar-divider" />
            <NavLink
              to="/lingxi"
              end
              className={({ isActive }) => `sidebar-link ${isActive ? "active" : ""}`}
            >
              <Search className="icon" size={16} />
              <span className="nav-label">查询与建表</span>
            </NavLink>
            <NavLink
              to="/lingxi/tasks"
              className={({ isActive }) => `sidebar-link ${isActive ? "active" : ""}`}
            >
              <ClipboardList className="icon" size={16} />
              <span className="nav-label">同步任务列表</span>
              <span id="lingxiTaskCountBadge" className="badge badge-gray" style={{ marginLeft: "auto" }}>
                {lingxiTasks.length}
              </span>
            </NavLink>
            <NavLink
              to="/lingxi/runs"
              className={({ isActive }) => `sidebar-link ${isActive ? "active" : ""}`}
            >
              <Clock3 className="icon" size={16} />
              <span className="nav-label">运行记录</span>
            </NavLink>
          </div>
        ) : isKeywordSection ? (
          /* 聚光关键词 导航组 (固定聚光在灵犀上方，板块层级始终一致) */
          <div id="sidebar-group-keyword" className="sidebar-nav">
            <button
              className="sidebar-link"
              type="button"
              onClick={() => navigate("/import")}
            >
              <LayoutDashboard className="icon" size={16} />
              <span className="nav-label">数据同步中心</span>
            </button>
            <div className="sidebar-divider" />
            <NavLink
              to="/keyword"
              end
              className={({ isActive }) => `sidebar-link ${isActive ? "active" : ""}`}
            >
              <Search className="icon" size={16} />
              <span className="nav-label">查询与建表</span>
            </NavLink>
            <NavLink
              to="/keyword/tasks"
              className={({ isActive }) => `sidebar-link ${isActive ? "active" : ""}`}
            >
              <ClipboardList className="icon" size={16} />
              <span className="nav-label">同步任务列表</span>
              <span id="kwTaskCountBadge" className="badge badge-gray" style={{ marginLeft: "auto" }}>
                {keywordTasks.length}
              </span>
            </NavLink>
            <NavLink
              to="/keyword/runs"
              className={({ isActive }) => `sidebar-link ${isActive ? "active" : ""}`}
            >
              <Clock3 className="icon" size={16} />
              <span className="nav-label">运行记录</span>
            </NavLink>
            <div className="sidebar-divider" />
            <button
              className="sidebar-link"
              type="button"
              onClick={() => navigate("/lingxi")}
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
              className={({ isActive }) => `nav-tab ${isActive ? "active" : ""}`}
            >
              <PlusCircle className="icon" size={16} />
              <span className="nav-label">新建同步任务</span>
            </NavLink>
            <NavLink
              to="/tasks"
              className={({ isActive }) => `nav-tab ${isActive ? "active" : ""}`}
            >
              <ClipboardList className="icon" size={16} />
              <span className="nav-label">同步任务</span>
              <span id="taskCountBadge" className="badge badge-gray" style={{ marginLeft: "auto" }}>
                {syncTasks.length}
              </span>
            </NavLink>
            <NavLink
              to="/runs"
              className={({ isActive }) => `nav-tab ${isActive ? "active" : ""}`}
            >
              <Clock3 className="icon" size={16} />
              <span className="nav-label">运行记录</span>
            </NavLink>
            <div className="sidebar-divider" />
            <button
              className="sidebar-link"
              type="button"
              onClick={() => navigate("/keyword")}
            >
              <BarChart3 className="icon" size={16} />
              <span className="nav-label">聚光关键词</span>
            </button>
            <button
              className="sidebar-link"
              type="button"
              onClick={() => navigate("/lingxi")}
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
        {isAdminSection && !isPromoUnlocked ? (
          <SimplePromoGatekeeper onUnlocked={() => setIsPromoUnlocked(true)} />
        ) : (
          <Outlet />
        )}
      </div>

      {/* 使用帮助 Drawer */}
      <div
        className="help-backdrop"
        style={{ display: helpDrawerOpen ? "block" : "none" }}
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
              全自动数据同步与简单投老笔记巡检暂停中心。
            </div>
            <div className="guide-list" style={{ marginTop: "16px" }}>
              <div className="guide-item">
                <span className="num">1</span>
                <div>
                  <strong>简单投老笔记暂停</strong>
                  <p>自动识别指定子账号下简单投老笔记，批量暂停避免预算偷跑，保留2026年新笔记。</p>
                </div>
              </div>
              <div className="guide-item">
                <span className="num">2</span>
                <div>
                  <strong>安全口令双重防护</strong>
                  <p>写操作需管理员口令验证，支持仅巡检预览（Dry Run）防误操作。</p>
                </div>
              </div>
              <div className="guide-item">
                <span className="num">3</span>
                <div>
                  <strong>定时任务与明细核对</strong>
                  <p>支持配置定时巡检规则与动态增删子账号，可随时下载 Excel/CSV 明细报表。</p>
                </div>
              </div>
            </div>
          </div>
        </aside>
      </div>
    </>
  );
};
