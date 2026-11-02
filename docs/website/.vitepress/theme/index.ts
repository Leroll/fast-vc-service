import DefaultTheme from 'vitepress/theme-without-fonts'
import Layout from './Layout.vue'
import ApiParameters from './components/ApiParameters.vue'
import ProtocolNav from './components/ProtocolNav.vue'
import './custom.css'

export default {
  extends: DefaultTheme,
  Layout,
  enhanceApp({ app }) {
    app.component('ApiParameters', ApiParameters)
    app.component('ProtocolNav', ProtocolNav)
  }
}
