const optionalUrl = (value) => (typeof value === 'string' ? value.trim() : '')

// 默认指向 Binizox 自有仓库；私有部署可以通过 Vite 构建变量替换入口。
export const PRODUCT_REPOSITORY_URL = optionalUrl(
  import.meta.env.VITE_BINIZOX_REPOSITORY_URL || 'https://github.com/Binizox/binizox'
)
export const PRODUCT_DOCUMENTATION_URL = optionalUrl(
  import.meta.env.VITE_BINIZOX_DOCUMENTATION_URL
)

export const productDocumentationUrl = (path = '') => {
  if (!PRODUCT_DOCUMENTATION_URL) return ''
  const base = PRODUCT_DOCUMENTATION_URL.endsWith('/')
    ? PRODUCT_DOCUMENTATION_URL
    : `${PRODUCT_DOCUMENTATION_URL}/`
  return new URL(String(path).replace(/^\/+/, ''), base).toString()
}
