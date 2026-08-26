import 'leaflet/dist/leaflet.css'
import './assets/main.css'
import { createApp } from 'vue'
import App from './App.vue'
import { API_KEY } from './composables/useApi.js'
import { defaultApi } from './api.js'

const app = createApp(App)

// 统一注入 api，组件通过 useApi() 获取；测试可覆盖同一个 key
app.provide(API_KEY, defaultApi)

app.mount('#app')
