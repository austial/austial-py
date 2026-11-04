"use client";

import { useSyncExternalStore } from "react";

/**
 * Sidebar collapsed state.
 *
 * The source of truth is `<html data-sidebar="collapsed">`, which the CSS reads. A tiny script in
 * <head> (SIDEBAR_INIT_SCRIPT) sets it from localStorage before first paint, so a collapsed sidebar
 * never flashes open on reload. React reads the attribute through useSyncExternalStore.
 */
const KEY = "austial:sidebar";
const EVENT = "austial:sidebar-change";

export const SIDEBAR_INIT_SCRIPT = `try{if(localStorage.getItem("${KEY}")==="collapsed")document.documentElement.dataset.sidebar="collapsed"}catch(e){}`;

const read = () => document.documentElement.dataset.sidebar === "collapsed";

function subscribe(callback) {
  window.addEventListener(EVENT, callback);
  return () => window.removeEventListener(EVENT, callback);
}

export function setSidebarCollapsed(collapsed) {
  document.documentElement.dataset.sidebar = collapsed ? "collapsed" : "open";
  try {
    localStorage.setItem(KEY, collapsed ? "collapsed" : "open");
  } catch {}
  window.dispatchEvent(new Event(EVENT));
}

export function toggleSidebar() {
  setSidebarCollapsed(!read());
}

/** true while the sidebar is collapsed (false during server render and hydration). */
export function useSidebarCollapsed() {
  return useSyncExternalStore(subscribe, read, () => false);
}
