import { setUnauthorizedHandler } from './services/http'
import { loginWithWechat } from './store/session'

App({
  onLaunch() {
    setUnauthorizedHandler(loginWithWechat)
  },
})
