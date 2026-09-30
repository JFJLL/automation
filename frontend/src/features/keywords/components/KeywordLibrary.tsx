import React, { useState, useRef, useEffect } from 'react';
import { Layers, Search, ChevronDown, ChevronUp, GripHorizontal } from 'lucide-react';

export interface KeywordLibraryProps {
  libraryData?: {
    categories: Record<string, Record<string, string[]>>;
    counts: Record<string, any>;
    all_keywords: string[];
  };
  selectedWords: string[];
  onToggleWord: (word: string) => void;
  onSelectMultipleWords: (words: string[]) => void;
}

export const KeywordLibrary: React.FC<KeywordLibraryProps> = ({
  libraryData,
  selectedWords,
  onToggleWord,
  onSelectMultipleWords,
}) => {
  const [collapsed, setCollapsed] = useState(false);
  const [filterText, setFilterText] = useState('');
  const [activeCategory, setActiveCategory] = useState<string>('全部');
  const [activeSubCategory, setActiveSubCategory] = useState<string>('');
  const [height, setHeight] = useState<number>(() => {
    return parseInt(localStorage.getItem('kw_lib_height') || '280', 10);
  });

  const isDraggingHeight = useRef(false);
  const startDragY = useRef(0);
  const startHeight = useRef(0);

  const containerRef = useRef<HTMLDivElement>(null);
  const isBoxSelecting = useRef(false);
  const selectionStart = useRef<{ x: number; y: number } | null>(null);
  const [selectionBox, setSelectionBox] = useState<{ x: number; y: number; w: number; h: number } | null>(null);

  // 高度拖拽调整
  const handlePointerDownResize = (e: React.PointerEvent) => {
    isDraggingHeight.current = true;
    startDragY.current = e.clientY;
    startHeight.current = height;
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
  };

  const handlePointerMoveResize = (e: React.PointerEvent) => {
    if (!isDraggingHeight.current) return;
    const delta = e.clientY - startDragY.current;
    const newH = Math.max(160, Math.min(700, startHeight.current + delta));
    setHeight(newH);
    localStorage.setItem('kw_lib_height', String(newH));
  };

  const handlePointerUpResize = (e: React.PointerEvent) => {
    isDraggingHeight.current = false;
    try {
      (e.target as HTMLElement).releasePointerCapture(e.pointerId);
    } catch {}
  };

  // 框选逻辑
  const handlePointerDownContainer = (e: React.PointerEvent) => {
    if ((e.target as HTMLElement).closest('.library-chip') || isDraggingHeight.current) return;
    if (!containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    isBoxSelecting.current = true;
    selectionStart.current = {
      x: e.clientX - rect.left + containerRef.current.scrollLeft,
      y: e.clientY - rect.top + containerRef.current.scrollTop,
    };
    setSelectionBox(null);
  };

  const handlePointerMoveContainer = (e: React.PointerEvent) => {
    if (!isBoxSelecting.current || !selectionStart.current || !containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const currX = e.clientX - rect.left + containerRef.current.scrollLeft;
    const currY = e.clientY - rect.top + containerRef.current.scrollTop;

    const x = Math.min(selectionStart.current.x, currX);
    const y = Math.min(selectionStart.current.y, currY);
    const w = Math.abs(currX - selectionStart.current.x);
    const h = Math.abs(currY - selectionStart.current.y);

    setSelectionBox({ x, y, w, h });
  };

  const handlePointerUpContainer = () => {
    if (isBoxSelecting.current && selectionBox && containerRef.current) {
      // 计算与 selectionBox 相交的关键词
      const chips = containerRef.current.querySelectorAll('.library-chip');
      const newlySelected: string[] = [];
      const contRect = containerRef.current.getBoundingClientRect();

      chips.forEach((c) => {
        const cRect = c.getBoundingClientRect();
        const cX = cRect.left - contRect.left + containerRef.current!.scrollLeft;
        const cY = cRect.top - contRect.top + containerRef.current!.scrollTop;
        const cW = cRect.width;
        const cH = cRect.height;

        const isIntersecting = !(
          cX + cW < selectionBox.x ||
          cX > selectionBox.x + selectionBox.w ||
          cY + cH < selectionBox.y ||
          cY > selectionBox.y + selectionBox.h
        );

        if (isIntersecting) {
          const w = c.getAttribute('data-word');
          if (w) newlySelected.push(w);
        }
      });

      if (newlySelected.length > 0) {
        onSelectMultipleWords(newlySelected);
      }
    }
    isBoxSelecting.current = false;
    selectionStart.current = null;
    setSelectionBox(null);
  };

  // 计算展示词项（完整词库，支持多级分类与搜索筛选，不硬切 150 词）
  const displayKeywords = React.useMemo(() => {
    if (!libraryData) return [];
    let words: string[] = [];
    if (activeCategory === '全部') {
      words = libraryData.all_keywords || [];
    } else if (libraryData.categories[activeCategory]) {
      const subCats = libraryData.categories[activeCategory];
      if (activeSubCategory && subCats[activeSubCategory]) {
        words = subCats[activeSubCategory];
      } else {
        Object.values(subCats).forEach((wList) => {
          words.push(...wList);
        });
      }
    }

    if (filterText.trim()) {
      const q = filterText.trim().toLowerCase();
      words = words.filter((w) => w.toLowerCase().includes(q));
    }
    return Array.from(new Set(words));
  }, [libraryData, activeCategory, activeSubCategory, filterText]);

  const categories = ['全部', '防晒衣', '冲锋衣', '户外鞋', '速干衣裤', '羽绒服', '背包配件'];
  const subCategories =
    activeCategory !== '全部' && libraryData?.categories[activeCategory]
      ? Object.keys(libraryData.categories[activeCategory])
      : [];

  return (
    <div
      style={{
        backgroundColor: '#ffffff',
        borderRadius: '12px',
        border: '1px solid #e2e8f0',
        overflow: 'hidden',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      {/* 词库 Header */}
      <div
        style={{
          padding: '12px 20px',
          backgroundColor: '#f8fafc',
          borderBottom: '1px solid #e2e8f0',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Layers size={16} color="#ea3445" />
          <span style={{ fontSize: '14px', fontWeight: 600, color: '#0f172a' }}>关键词库索引</span>
          <span style={{ fontSize: '12px', color: '#94a3b8' }}>
            共 {libraryData?.counts?.total || 0} 个词项，当前展示 {displayKeywords.length} 个 (支持鼠标拖拽框选)
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          {/* 实时筛选框 */}
          <div style={{ position: 'relative', width: '200px' }}>
            <Search size={14} style={{ position: 'absolute', left: '8px', top: '8px', color: '#94a3b8' }} />
            <input
              type="text"
              placeholder="搜索词库词项..."
              value={filterText}
              onChange={(e) => setFilterText(e.target.value)}
              style={{
                width: '100%',
                padding: '5px 10px 5px 28px',
                borderRadius: '6px',
                border: '1px solid #cbd5e1',
                fontSize: '12px',
                outline: 'none',
              }}
            />
          </div>
          <button
            type="button"
            onClick={() => setCollapsed(!collapsed)}
            style={{
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              color: '#64748b',
              display: 'flex',
              alignItems: 'center',
              gap: '4px',
              fontSize: '12px',
            }}
          >
            {collapsed ? (
              <>
                展开词库 <ChevronDown size={14} />
              </>
            ) : (
              <>
                收起词库 <ChevronUp size={14} />
              </>
            )}
          </button>
        </div>
      </div>

      {!collapsed && (
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          {/* 一级分类 */}
          <div
            style={{
              display: 'flex',
              borderBottom: '1px solid #f1f5f9',
              padding: '0 16px',
              overflowX: 'auto',
              backgroundColor: '#ffffff',
            }}
          >
            {categories.map((cat) => {
              const isAct = activeCategory === cat;
              return (
                <button
                  key={cat}
                  type="button"
                  onClick={() => {
                    setActiveCategory(cat);
                    setActiveSubCategory('');
                  }}
                  style={{
                    padding: '9px 14px',
                    fontSize: '13px',
                    fontWeight: isAct ? 600 : 500,
                    color: isAct ? '#ea3445' : '#64748b',
                    borderBottom: isAct ? '2px solid #ea3445' : '2px solid transparent',
                    background: 'none',
                    border: 'none',
                    cursor: 'pointer',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {cat}
                </button>
              );
            })}
          </div>

          {/* 二级子分类 (Section 二十三 parity) */}
          {subCategories.length > 0 && (
            <div
              style={{
                display: 'flex',
                gap: '6px',
                padding: '8px 16px',
                backgroundColor: '#fafbfc',
                borderBottom: '1px solid #f1f5f9',
                overflowX: 'auto',
              }}
            >
              <button
                type="button"
                onClick={() => setActiveSubCategory('')}
                style={{
                  padding: '3px 8px',
                  borderRadius: '4px',
                  fontSize: '11px',
                  fontWeight: 500,
                  border: 'none',
                  cursor: 'pointer',
                  backgroundColor: activeSubCategory === '' ? '#ea3445' : '#f1f5f9',
                  color: activeSubCategory === '' ? '#ffffff' : '#475569',
                }}
              >
                全部子类
              </button>
              {subCategories.map((sub) => {
                const isSubAct = activeSubCategory === sub;
                return (
                  <button
                    key={sub}
                    type="button"
                    onClick={() => setActiveSubCategory(sub)}
                    style={{
                      padding: '3px 8px',
                      borderRadius: '4px',
                      fontSize: '11px',
                      fontWeight: 500,
                      border: 'none',
                      cursor: 'pointer',
                      backgroundColor: isSubAct ? '#ea3445' : '#f1f5f9',
                      color: isSubAct ? '#ffffff' : '#475569',
                    }}
                  >
                    {sub}
                  </button>
                );
              })}
            </div>
          )}

          {/* 词项平铺与框选容器 */}
          <div
            ref={containerRef}
            onPointerDown={handlePointerDownContainer}
            onPointerMove={handlePointerMoveContainer}
            onPointerUp={handlePointerUpContainer}
            style={{
              height: `${height}px`,
              overflowY: 'auto',
              padding: '16px 20px',
              display: 'flex',
              flexWrap: 'wrap',
              gap: '8px',
              alignContent: 'flex-start',
              position: 'relative',
              userSelect: 'none',
            }}
          >
            {/* 框选矩形浮层 */}
            {selectionBox && (
              <div
                style={{
                  position: 'absolute',
                  left: `${selectionBox.x}px`,
                  top: `${selectionBox.y}px`,
                  width: `${selectionBox.w}px`,
                  height: `${selectionBox.h}px`,
                  backgroundColor: 'rgba(234, 52, 69, 0.15)',
                  border: '1px dashed #ea3445',
                  pointerEvents: 'none',
                  zIndex: 20,
                }}
              />
            )}

            {displayKeywords.map((word) => {
              const isSelected = selectedWords.includes(word);
              return (
                <span
                  key={word}
                  data-word={word}
                  className="library-chip"
                  onClick={() => onToggleWord(word)}
                  style={{
                    padding: '4px 10px',
                    borderRadius: '6px',
                    fontSize: '12px',
                    cursor: 'pointer',
                    border: '1px solid ' + (isSelected ? '#ea3445' : '#e2e8f0'),
                    backgroundColor: isSelected ? '#fef2f2' : '#ffffff',
                    color: isSelected ? '#ea3445' : '#475569',
                    transition: 'border-color 0.1s, background-color 0.1s',
                  }}
                >
                  {word}
                </span>
              );
            })}
          </div>

          {/* 高度调整手柄 (Section 二十五 parity) */}
          <div
            onPointerDown={handlePointerDownResize}
            onPointerMove={handlePointerMoveResize}
            onPointerUp={handlePointerUpResize}
            title="拖拽上下调整词库区域高度"
            style={{
              height: '10px',
              backgroundColor: '#f1f5f9',
              borderTop: '1px solid #e2e8f0',
              cursor: 'ns-resize',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <GripHorizontal size={14} color="#94a3b8" />
          </div>
        </div>
      )}
    </div>
  );
};

