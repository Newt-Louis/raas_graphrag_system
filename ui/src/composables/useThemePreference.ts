import { computed, onMounted, onUnmounted, ref, watch } from 'vue'

export type ThemeMode = 'light' | 'dark' | 'system'

const STORAGE_KEY = 'raas-platform-theme-mode'
const themeMode = ref<ThemeMode>(readStoredMode())
const systemPrefersDark = ref(false)
let initialized = false
let mediaQuery: MediaQueryList | null = null

function readStoredMode(): ThemeMode {
  if (typeof window === 'undefined') return 'system'

  const stored = window.localStorage.getItem(STORAGE_KEY)
  if (stored === 'light' || stored === 'dark' || stored === 'system') {
    return stored
  }
  return 'system'
}

function applyTheme(mode: ThemeMode, prefersDark: boolean) {
  if (typeof document === 'undefined') return

  const isDark = mode === 'dark' || (mode === 'system' && prefersDark)
  document.documentElement.classList.toggle('app-dark', isDark)
  document.documentElement.setAttribute('data-theme', isDark ? 'dark' : 'light')
}

export function useThemePreference() {
  if (!initialized && typeof window !== 'undefined') {
    initialized = true
    mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
    systemPrefersDark.value = mediaQuery.matches
    applyTheme(themeMode.value, systemPrefersDark.value)

    watch(
      [themeMode, systemPrefersDark],
      ([mode, prefersDark]) => {
        window.localStorage.setItem(STORAGE_KEY, mode)
        applyTheme(mode, prefersDark)
      },
      { immediate: true },
    )
  }

  onMounted(() => {
    if (!mediaQuery) return

    const listener = (event: MediaQueryListEvent) => {
      systemPrefersDark.value = event.matches
    }
    mediaQuery.addEventListener('change', listener)
    onUnmounted(() => mediaQuery?.removeEventListener('change', listener))
  })

  return {
    themeMode,
    effectiveTheme: computed(() =>
      themeMode.value === 'system' ? (systemPrefersDark.value ? 'dark' : 'light') : themeMode.value,
    ),
    setThemeMode: (mode: ThemeMode) => {
      themeMode.value = mode
    },
  }
}
