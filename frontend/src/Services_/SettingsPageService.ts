// frontend/src/Services_/SettingsPageService.ts

/**
 * 设置页只管理前端本地偏好，不依赖后端账户模型。
 */
export interface AppSettings {
  fontScale: number
  skipOutputAnimation: boolean
  autoScrollChat: boolean
  defaultDebugMode: boolean
}

const SETTINGS_STORAGE_KEY = 'trpg-app-settings'
export const APP_SETTINGS_UPDATED_EVENT = 'trpg:app-settings-updated'

/**
 * 默认配置保持保守，避免影响现有界面行为。
 */
export const DEFAULT_APP_SETTINGS: AppSettings = {
  fontScale: 100,
  skipOutputAnimation: false,
  autoScrollChat: true,
  defaultDebugMode: false,
}

/**
 * 从本地存储加载设置；解析失败时直接回退默认值。
 */
export function loadAppSettings(): AppSettings {
  const rawValue = localStorage.getItem(SETTINGS_STORAGE_KEY)
  if (!rawValue) {
    return { ...DEFAULT_APP_SETTINGS }
  }

  try {
    const parsed = JSON.parse(rawValue) as Partial<AppSettings>
    const parsedFontScale = typeof parsed.fontScale === 'number' ? parsed.fontScale : DEFAULT_APP_SETTINGS.fontScale
    return {
      fontScale: Math.min(120, Math.max(85, parsedFontScale)),
      skipOutputAnimation: parsed.skipOutputAnimation ?? DEFAULT_APP_SETTINGS.skipOutputAnimation,
      autoScrollChat: parsed.autoScrollChat ?? DEFAULT_APP_SETTINGS.autoScrollChat,
      defaultDebugMode: parsed.defaultDebugMode ?? DEFAULT_APP_SETTINGS.defaultDebugMode,
    }
  } catch {
    return { ...DEFAULT_APP_SETTINGS }
  }
}

/**
 * 保存当前设置，统一由设置页调用。
 */
export function saveAppSettings(settings: AppSettings): void {
  localStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(settings))
  window.dispatchEvent(new CustomEvent(APP_SETTINGS_UPDATED_EVENT, { detail: settings }))
}

/**
 * 恢复默认设置，并把结果返回给页面直接使用。
 */
export function resetAppSettings(): AppSettings {
  const resetValue = { ...DEFAULT_APP_SETTINGS }
  saveAppSettings(resetValue)
  return resetValue
}
