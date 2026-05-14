import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'

export function useEmbedConfig() {
  const route = useRoute()
  const config = ref({
    primaryColor: '#3b82f6',
    theme: 'light',
    apiKey: '',
  })

  onMounted(() => {
    // Đọc từ URL query
    const query = route.query
    if (query.primary_color) {
      config.value.primaryColor = decodeURIComponent(query.primary_color as string)
      document.documentElement.style.setProperty(
        '--primary-color',
        config.value.primaryColor
      )
    }
    if (query.theme) {
      config.value.theme = query.theme as string
      document.documentElement.setAttribute('data-theme', config.value.theme)
    }

    // Lắng nghe postMessage từ host app (để update real-time)
    window.addEventListener('message', (event) => {
      if (event.data.type === 'UPDATE_THEME') {
        document.documentElement.style.setProperty(
          '--primary-color',
          event.data.primaryColor
        )
      }
    })
  })

  return { config }
}