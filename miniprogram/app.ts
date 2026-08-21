import { setUnauthorizedHandler } from './services/http'
import { getSession, loginWithWechat } from './store/session'

App({
  async onLaunch() {
    setUnauthorizedHandler(loginWithWechat)
    if (!getSession()) {
      try {
        await loginWithWechat()
      } catch {
        // Pages render their recoverable offline state and can trigger login again.
      }
    }
  },
})
