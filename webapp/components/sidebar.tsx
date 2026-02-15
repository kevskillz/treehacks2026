'use client'

import Link from 'next/link'
import Image from 'next/image'
import { usePathname } from 'next/navigation'
import { useState, useEffect, createContext, useContext } from 'react'
import { cn } from '@/lib/utils'
import { ThemeSwitcher } from './theme-switcher'
import { AsciiBackground } from './ascii-background'

export interface MonitoringItem {
  id: string
  title: string
  status: 'active' | 'paused' | 'completed' | 'pending' | 'failed'
  type: 'tweet' | 'reply' | 'mention'
}

const defaultMonitorings: MonitoringItem[] = []

const SidebarContext = createContext<{
  isCollapsed: boolean
  setIsCollapsed: (value: boolean) => void
}>({
  isCollapsed: false,
  setIsCollapsed: () => {},
})

export const useSidebar = () => useContext(SidebarContext)

function Logo({ isCollapsed }: { isCollapsed: boolean }) {
  return (
    <div className={cn("flex items-center gap-2.5", isCollapsed && "justify-center")}>
      <div className="flex h-7 w-7 items-center justify-center rounded-md bg-foreground flex-shrink-0">
        <Image
          src="/Logo.png"
          alt="Matrix logo"
          width={20}
          height={20}
          className="h-5 w-5 rounded-sm invert dark:invert-0"
          priority
        />
      </div>
      {!isCollapsed && (
        <span className="text-sm font-semibold text-foreground tracking-tight whitespace-nowrap">
          Matrix
        </span>
      )}
    </div>
  )
}

function CollapseToggleButton({ isCollapsed, onClick }: { isCollapsed: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="sidebar-toggle flex h-5 w-5 items-center justify-center rounded-full border bg-background shadow-sm hover:bg-accent transition-colors"
      aria-label={isCollapsed ? "Expand sidebar" : "Collapse sidebar"}
    >
      <svg
        className={cn("h-3 w-3 text-muted-foreground transition-transform duration-200", isCollapsed && "rotate-180")}
        fill="none" stroke="currentColor" viewBox="0 0 24 24"
      >
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
      </svg>
    </button>
  )
}

function SearchButton({ isCollapsed }: { isCollapsed: boolean }) {
  if (isCollapsed) {
    return (
      <button className="flex h-8 w-8 items-center justify-center rounded-lg border bg-background text-muted-foreground transition-colors hover:bg-accent hover:text-foreground mx-auto">
        <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
        </svg>
      </button>
    )
  }

  return (
    <button className="flex w-full items-center gap-2 rounded-lg border bg-background px-3 py-1.5 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-foreground">
      <svg className="h-3.5 w-3.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
      </svg>
      <span className="flex-1 text-left text-xs whitespace-nowrap">Search...</span>
      <kbd className="pointer-events-none rounded border bg-muted px-1 py-0.5 text-[10px] text-muted-foreground">⌘K</kbd>
    </button>
  )
}

function StatusDot({ status }: { status: MonitoringItem['status'] }) {
  return (
    <span className={cn(
      'h-1.5 w-1.5 rounded-full',
      status === 'active' && 'bg-emerald-500',
      status === 'paused' && 'bg-amber-500',
      status === 'completed' && 'bg-slate-400',
      status === 'pending' && 'bg-blue-500',
      status === 'failed' && 'bg-red-500'
    )} />
  )
}

function MonitoringItemLink({ item, isCollapsed }: { item: MonitoringItem; isCollapsed: boolean }) {
  return (
    <Link
      href={`/features/${item.id}`}
      className={cn(
        "flex items-center gap-2 rounded-md px-2.5 py-1.5 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-foreground",
        isCollapsed && "justify-center px-0"
      )}
      title={isCollapsed ? item.title : undefined}
    >
      <StatusDot status={item.status} />
      <span className={cn("flex-1 truncate", isCollapsed && "hidden")}>{item.title}</span>
    </Link>
  )
}

interface SidebarProps {
  userSection?: React.ReactNode
  monitorings?: MonitoringItem[]
  isCollapsed: boolean
  onToggleCollapse: () => void
}

export function Sidebar({ userSection, monitorings = defaultMonitorings, isCollapsed, onToggleCollapse }: SidebarProps) {
  const pathname = usePathname()

  return (
    <aside className={cn(
      "sidebar fixed left-0 top-0 z-30 flex h-screen flex-col border-r bg-background",
      isCollapsed && "collapsed"
    )}>
      <CollapseToggleButton isCollapsed={isCollapsed} onClick={onToggleCollapse} />

      {/* Header */}
      <div className={cn(
        "flex h-14 items-center border-b px-3",
        isCollapsed ? "justify-center" : "justify-between"
      )}>
        <Link href="/"><Logo isCollapsed={isCollapsed} /></Link>
        {!isCollapsed && <ThemeSwitcher />}
      </div>

      {/* Search */}
      <div className="p-3">
        <SearchButton isCollapsed={isCollapsed} />
      </div>

      {/* Navigation */}
      <nav className={cn("flex-1 overflow-y-auto px-2 pb-4 space-y-5", isCollapsed && "overflow-x-hidden")}>
        <ul className="space-y-0.5">
          <li>
            <Link
              href="/features"
              className={cn(
                'flex items-center gap-2 rounded-lg px-2.5 py-1.5 text-sm transition-colors',
                pathname === '/features'
                  ? 'bg-accent text-foreground font-medium'
                  : 'text-muted-foreground hover:text-foreground hover:bg-accent',
                isCollapsed && "justify-center px-0"
              )}
              title={isCollapsed ? "Projects" : undefined}
            >
              <svg className="h-4 w-4 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
              </svg>
              <span className={cn("whitespace-nowrap", isCollapsed && "hidden")}>Projects</span>
            </Link>
          </li>
        </ul>

        {/* Active */}
        <div className="mb-5">
          <div className={cn("flex items-center justify-between px-2.5 mb-1.5", isCollapsed && "justify-center px-0")}>
            <h3 className={cn("text-[10px] font-medium uppercase tracking-wider text-muted-foreground whitespace-nowrap", isCollapsed && "hidden")}>
              Active
            </h3>
            {!isCollapsed && (
              <Link href="/features?new=1" className="text-[10px] text-muted-foreground hover:text-foreground transition-colors">+ New</Link>
            )}
          </div>
          <ul className="space-y-0.5">
            {monitorings.filter(m => m.status === 'active' || m.status === 'pending').map((item) => (
              <li key={item.id}><MonitoringItemLink item={item} isCollapsed={isCollapsed} /></li>
            ))}
          </ul>
        </div>

        {monitorings.some(m => m.status === 'paused') && (
          <div className="mb-5">
            <h3 className={cn("mb-1.5 px-2.5 text-[10px] font-medium uppercase tracking-wider text-muted-foreground whitespace-nowrap", isCollapsed && "hidden")}>Paused</h3>
            <ul className="space-y-0.5">
              {monitorings.filter(m => m.status === 'paused').map((item) => (
                <li key={item.id}><MonitoringItemLink item={item} isCollapsed={isCollapsed} /></li>
              ))}
            </ul>
          </div>
        )}

        {monitorings.some(m => m.status === 'completed') && (
          <div className="mb-5">
            <h3 className={cn("mb-1.5 px-2.5 text-[10px] font-medium uppercase tracking-wider text-muted-foreground whitespace-nowrap", isCollapsed && "hidden")}>Done</h3>
            <ul className="space-y-0.5">
              {monitorings.filter(m => m.status === 'completed').map((item) => (
                <li key={item.id}><MonitoringItemLink item={item} isCollapsed={isCollapsed} /></li>
              ))}
            </ul>
          </div>
        )}

        {monitorings.some(m => m.status === 'failed') && (
          <div className="mb-5">
            <h3 className={cn("mb-1.5 px-2.5 text-[10px] font-medium uppercase tracking-wider text-muted-foreground whitespace-nowrap", isCollapsed && "hidden")}>Failed</h3>
            <ul className="space-y-0.5">
              {monitorings.filter(m => m.status === 'failed').map((item) => (
                <li key={item.id}><MonitoringItemLink item={item} isCollapsed={isCollapsed} /></li>
              ))}
            </ul>
          </div>
        )}
      </nav>

      <div className={cn("mt-auto border-t", isCollapsed ? "p-2" : "p-3")}>{userSection}</div>
    </aside>
  )
}

interface SidebarLayoutProps {
  children: React.ReactNode
  userSection?: React.ReactNode
  monitorings?: MonitoringItem[]
}

const SIDEBAR_STORAGE_KEY = 'sidebar-collapsed'

export function SidebarLayout({ children, userSection, monitorings }: SidebarLayoutProps) {
  const [isCollapsed, setIsCollapsed] = useState(() => {
    if (typeof window !== 'undefined') {
      const stored = localStorage.getItem(SIDEBAR_STORAGE_KEY)
      return stored === 'true'
    }
    return false
  })

  useEffect(() => {
    localStorage.setItem(SIDEBAR_STORAGE_KEY, String(isCollapsed))
  }, [isCollapsed])

  return (
    <SidebarContext.Provider value={{ isCollapsed, setIsCollapsed }}>
      <div className="flex min-h-screen overflow-x-hidden">
        <Sidebar
          userSection={userSection}
          monitorings={monitorings}
          isCollapsed={isCollapsed}
          onToggleCollapse={() => setIsCollapsed(!isCollapsed)}
        />
        <main
          className="relative flex-1 min-w-0 overflow-x-hidden transition-[margin-left] duration-200 ease-in-out"
          style={{ marginLeft: isCollapsed ? 'var(--sidebar-collapsed-width)' : 'var(--sidebar-width)' }}
        >
          <AsciiBackground variant="light" />
          <div className="relative min-h-screen">{children}</div>
        </main>
      </div>
    </SidebarContext.Provider>
  )
}
