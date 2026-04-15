/**
 * Workspace 专用图标
 * 
 * 风格：与 Icons.tsx 一致 — 手绘感线条，1.5px stroke，round caps
 */

const I = ({ children, className = '' }: { children: React.ReactNode; className?: string }) => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor"
    strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"
    className={`text-current ${className}`}>
    {children}
  </svg>
)

/** 文件夹 */
export function FolderIcon({ className }: { className?: string }) {
  return <I className={className}>
    <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
  </I>
}

/** 文本文件 */
export function FileTextIcon({ className }: { className?: string }) {
  return <I className={className}>
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
    <polyline points="14 2 14 8 20 8" />
    <line x1="16" y1="13" x2="8" y2="13" />
    <line x1="16" y1="17" x2="8" y2="17" />
    <polyline points="10 9 9 9 8 9" />
  </I>
}

/** 代码文件 */
export function FileCodeIcon({ className }: { className?: string }) {
  return <I className={className}>
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
    <polyline points="14 2 14 8 20 8" />
    <path d="M10 12l-2 2 2 2" />
    <path d="M14 12l2 2-2 2" />
  </I>
}

/** 关闭 */
export function CloseIcon({ className }: { className?: string }) {
  return <I className={className}>
    <line x1="18" y1="6" x2="6" y2="18" />
    <line x1="6" y1="6" x2="18" y2="18" />
  </I>
}

/** 终端 */
export function TerminalIcon({ className }: { className?: string }) {
  return <I className={className}>
    <polyline points="4 17 10 11 4 5" />
    <line x1="12" y1="19" x2="20" y2="19" />
  </I>
}

/** 小地球（浏览器） */
export function GlobeSmallIcon({ className }: { className?: string }) {
  return <I className={className}>
    <circle cx="12" cy="12" r="10" />
    <line x1="2" y1="12" x2="22" y2="12" />
    <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
  </I>
}

/** 垃圾桶 */
export function TrashIcon({ className }: { className?: string }) {
  return <I className={className}>
    <polyline points="3 6 5 6 21 6" />
    <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
  </I>
}

/** 刷新 */
export function RefreshIcon({ className }: { className?: string }) {
  return <I className={className}>
    <polyline points="23 4 23 10 17 10" />
    <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
  </I>
}

/** 分屏/面板 */
export function PanelRightIcon({ className }: { className?: string }) {
  return <I className={className}>
    <rect x="3" y="3" width="18" height="18" rx="2" />
    <line x1="15" y1="3" x2="15" y2="21" />
  </I>
}

/** 收起面板 */
export function PanelCloseIcon({ className }: { className?: string }) {
  return <I className={className}>
    <rect x="3" y="3" width="18" height="18" rx="2" />
    <line x1="15" y1="3" x2="15" y2="21" />
    <path d="M19 9l-3 3 3 3" />
  </I>
}
