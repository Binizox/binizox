<script setup>
import { ref, computed } from 'vue'
import { withBase } from 'vitepress'

const GITHUB = (import.meta.env.VITE_BINIZOX_REPOSITORY_URL || '').trim()
const DEMO = (import.meta.env.VITE_BINIZOX_DEMO_URL || '').trim()

// 使用稳定、可直接验证的能力标签，避免首页数据随版本漂移。
const stats = [
  { value: 'RAG + KG', label: '统一知识引擎' },
  { value: 'MCP + Skills', label: '可扩展智能体' },
  { value: 'Multi-tenant', label: '用户与部门权限' },
  { value: 'MIT', label: '开源可自托管' }
]

// Harness 能力中枢（bento）
const capabilities = [
  {
    icon: 'box', span: true,
    title: '沙盒文件系统',
    desc: 'Agent 在当前 Project Workdir 中读写文件，产物自动落盘；Viewer 与交付物入口可以读取同一份持久文件，并支持文本、图片、PDF、HTML 预览与下载。',
    tags: ['预览', '下载', 'Artifacts 产物'],
    shot: 'https://xerrors.oss-cn-shanghai.aliyuncs.com/github/image-20260604203704426.png'
  },
  {
    icon: 'sparkles',
    title: 'Skills 技能系统',
    desc: '把图像生成、深度研究、数据报表等工作方式封装成可复用技能，支持上传与远程安装，并在确认前预览内容。',
    tags: ['内置', '上传', '远程']
  },
  {
    icon: 'plug',
    title: 'MCP 集成',
    desc: '通过 Model Context Protocol 标准协议接入外部工具服务，统一启停与权限管理。',
    tags: ['标准协议']
  },
  {
    icon: 'wrench',
    title: '内置工具',
    desc: 'present_artifacts 交付产物、提问中断等待用户、按需安装技能、联网检索等开箱即用。',
    tags: ['开箱即用']
  },
  {
    icon: 'fork',
    title: '子智能体 SubAgents',
    desc: '主智能体可以把复杂任务交给子智能体；子智能体使用独立 child thread，和父智能体共享授权的 Workdir 并回传结果。',
    tags: ['隔离编排']
  },
  {
    icon: 'layers',
    title: '中间件编排',
    desc: '知识库检索注入、附件处理、历史摘要 offload、动态工具注入等中间件可组合编排。',
    tags: ['可组合']
  },
  {
    icon: 'cpu',
    title: '异步 Worker',
    desc: '基于 ARQ 的后台任务，将分钟到小时级长耗时任务异步执行，支持取消与流式输出。',
    tags: ['长任务', '可取消', '流式']
  }
]

// 知识引擎：可切换的能力 tab，右侧媒体随选中项切换
const engineTabs = [
  {
    key: 'parse', icon: 'scan', title: '多格式解析',
    desc: 'MinerU、PaddleX、RapidOCR 统一解析 PDF、Office、图片等为结构化 Markdown。',
    shot: 'https://xerrors.oss-cn-shanghai.aliyuncs.com/github/image-20260605205221908.png'
  },
  {
    key: 'retrieval', icon: 'database', title: 'Agentic RAG',
    desc: '智能体自主决定检索时机与查询，多轮向量检索 + Rerank，回答带可溯源引用。',
    shot: 'https://xerrors.oss-cn-shanghai.aliyuncs.com/github/image-20260604205342546.png'
  },
  {
    key: 'graph', icon: 'share', title: '知识图谱',
    desc: '抽取实体与关系构建知识图谱，子图检索参与增强，并支持可视化探索。',
    shot: 'https://xerrors.oss-cn-shanghai.aliyuncs.com/github/image-20260604204056298.png'
  },
  {
    key: 'eval', icon: 'chart', title: '检索评估',
    desc: '内置检索质量评估，支持命名运行与指标对比，量化召回与回答效果。',
    shot: 'https://xerrors.oss-cn-shanghai.aliyuncs.com/github/image-20260604210111977.png'
  },
  {
    key: 'sources', icon: 'plug', title: '多知识源接入',
    desc: '支持 Dify、Notion 等外部只读知识源接入，统一检索与引用。',
    shot: 'https://xerrors.oss-cn-shanghai.aliyuncs.com/github/image-20260604205611168.png'
  }
]
const activeEngine = ref(0)
const currentEngine = computed(() => engineTabs[activeEngine.value])

// 模型供应商墙（横向跑马灯，两行错位反向滚动）
const ICON_BASE = 'https://registry.npmmirror.com/@lobehub/icons-static-svg/latest/files/icons'
const providers = [
  { name: 'OpenAI', icon: `${ICON_BASE}/openai.svg` },
  { name: 'DeepSeek', icon: `${ICON_BASE}/deepseek-color.svg` },
  { name: '通义千问', icon: `${ICON_BASE}/bailian-color.svg` },
  { name: '智谱 AI', icon: `${ICON_BASE}/zhipu-color.svg` },
  { name: 'Moonshot', icon: `${ICON_BASE}/moonshot.svg` },
  { name: 'MiniMax', icon: `${ICON_BASE}/minimax-color.svg` },
  { name: 'SiliconFlow', icon: `${ICON_BASE}/siliconcloud-color.svg` },
  { name: 'OpenRouter', icon: `${ICON_BASE}/openrouter.svg` },
  { name: 'ModelScope', icon: `${ICON_BASE}/modelscope-color.svg` },
  { name: 'OpenCode', icon: `${ICON_BASE}/opencode.svg` },
  { name: '小米 MiMo', icon: `${ICON_BASE}/xiaomimimo.svg` }
]
// 第二行换个起始顺序以形成错位；每行内容复制一份用于无缝循环
const providersTop = [...providers, ...providers]
const providersBottom = (() => {
  const rotated = [...providers.slice(5), ...providers.slice(0, 5)]
  return [...rotated, ...rotated]
})()

// 工作原理
const steps = [
  { n: '01', title: '配置底座', desc: '管理员接入模型供应商、构建知识库与知识图谱、划分用户与部门权限。' },
  { n: '02', title: '编排智能体', desc: '为 Agent 挂载 Skills、MCP、Tools 与子智能体，组合所需中间件能力。' },
  { n: '03', title: '检索与推理', desc: '对话中融合向量检索与知识图谱推理，沙盒工具执行真实任务。' },
  { n: '04', title: '交付产物', desc: '返回带引用来源的回答，并以可预览、可下载的产物卡片交付结果。' }
]

// 产品截图一览
const shots = [
  {
    title: '对话工作台',
    desc: '统一完成智能体对话、知识引用与产物交付',
    image: 'https://xerrors.oss-cn-shanghai.aliyuncs.com/github/image-20260326125852369.png'
  },
  {
    title: '智能体配置',
    desc: '挂载 Skills、MCP、子智能体与中间件',
    image: 'https://xerrors.oss-cn-shanghai.aliyuncs.com/github/image-20260326130528866.png'
  },
  {
    title: '知识图谱',
    desc: '构建、检索并可视化实体关系与子图',
    image: 'https://github.com/user-attachments/assets/fc46a14b-16fb-47ea-84a0-148a451f3012'
  },
  {
    title: '组织权限',
    desc: '按用户和部门管理知识与平台能力',
    image: 'https://github.com/user-attachments/assets/13bd22ea-ddde-4262-8c29-69fb948bce44'
  }
]

// 企业级
const enterprise = [
  { icon: 'shield', title: '多租户与权限', desc: '用户 / 部门级隔离，知识库支持全局、部门、指定人三档共享。' },
  { icon: 'key', title: 'API Key 集成', desc: '签发独立密钥，供外部系统以 API 方式安全调用平台能力。' },
  { icon: 'layers', title: 'LITE 轻量启动', desc: 'make up-lite 跳过重依赖快速冷启动，Docker Compose 开箱即用。' }
]

// 应用场景
const cases = [
  { title: '内部知识服务', desc: '把制度、产品和技术资料变成有权限边界、带来源引用的知识助手。' },
  { title: '研究与内容交付', desc: '让智能体检索资料、调用工具并交付报告、图表、网页等可下载产物。' },
  { title: '组织级 Agent 平台', desc: '统一管理模型、知识、工具和扩展能力，为业务系统提供可调用的 Agent 服务。' }
]

// 技术栈分层
const techStack = [
  { group: '前端', items: ['Vue 3', 'Vite', 'Pinia'] },
  { group: '后端', items: ['FastAPI', 'LangGraph', 'ARQ'] },
  { group: '存储', items: ['PostgreSQL', 'Redis', 'MinIO', 'Milvus', 'Neo4j'] },
  { group: '解析', items: ['MinerU', 'PaddleX', 'RapidOCR'] },
  { group: '部署', items: ['Docker Compose'] }
]

// 开源致谢
const credits = [
  { name: 'LightRAG', url: 'https://github.com/HKUDS/LightRAG' },
  { name: 'DeepAgents', url: 'https://github.com/langchain-ai/deepagents' },
  { name: 'DeerFlow', url: 'https://github.com/bytedance/deer-flow' },
  { name: 'RAGFlow', url: 'https://github.com/infiniflow/ragflow' },
  { name: 'LangGraph', url: 'https://github.com/langchain-ai/langgraph' },
  { name: 'QwenPaw', url: 'https://github.com/agentscope-ai/QwenPaw' }
]

// lucide 风格图标路径（stroke 1.5）
const icons = {
  box: '<path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z"/><path d="m3.3 7 8.7 5 8.7-5"/><path d="M12 22V12"/>',
  sparkles: '<path d="M9.94 15.5A2 2 0 0 0 8.5 14.06l-6.14-1.58a.5.5 0 0 1 0-.96L8.5 9.94A2 2 0 0 0 9.94 8.5l1.58-6.14a.5.5 0 0 1 .96 0L14.06 8.5A2 2 0 0 0 15.5 9.94l6.14 1.58a.5.5 0 0 1 0 .96L15.5 14.06a2 2 0 0 0-1.44 1.44l-1.58 6.14a.5.5 0 0 1-.96 0z"/>',
  plug: '<path d="M12 22v-5"/><path d="M9 7V2"/><path d="M15 7V2"/><path d="M6 13V8h12v5a4 4 0 0 1-4 4h-4a4 4 0 0 1-4-4Z"/>',
  wrench: '<path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>',
  fork: '<circle cx="12" cy="18" r="3"/><circle cx="6" cy="6" r="3"/><circle cx="18" cy="6" r="3"/><path d="M18 9v2c0 .6-.4 1-1 1H7c-.6 0-1-.4-1-1V9"/><path d="M12 12v3"/>',
  layers: '<path d="M12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83Z"/><path d="m22 17.65-9.17 4.16a2 2 0 0 1-1.66 0L2 17.65"/><path d="m22 12.65-9.17 4.16a2 2 0 0 1-1.66 0L2 12.65"/>',
  cpu: '<rect width="16" height="16" x="4" y="4" rx="2"/><rect width="6" height="6" x="9" y="9" rx="1"/><path d="M15 2v2"/><path d="M15 20v2"/><path d="M2 15h2"/><path d="M2 9h2"/><path d="M20 15h2"/><path d="M20 9h2"/><path d="M9 2v2"/><path d="M9 20v2"/>',
  database: '<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14a9 3 0 0 0 18 0V5"/><path d="M3 12a9 3 0 0 0 18 0"/>',
  share: '<circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.59" x2="15.42" y1="13.51" y2="17.49"/><line x1="15.41" x2="8.59" y1="6.51" y2="10.49"/>',
  scan: '<path d="M3 7V5a2 2 0 0 1 2-2h2"/><path d="M17 3h2a2 2 0 0 1 2 2v2"/><path d="M21 17v2a2 2 0 0 1-2 2h-2"/><path d="M7 21H5a2 2 0 0 1-2-2v-2"/><path d="M7 12h10"/>',
  shield: '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/>',
  key: '<path d="m15.5 7.5 2.3 2.3a1 1 0 0 0 1.4 0l2.1-2.1a1 1 0 0 0 0-1.4L19 4"/><path d="m21 2-9.6 9.6"/><circle cx="7.5" cy="15.5" r="5.5"/>',
  rocket: '<path d="M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 2.18 0 0 0-2.91-.09z"/><path d="m12 15-3-3a22 22 0 0 1 2-3.95A12.88 12.88 0 0 1 22 2c0 2.72-.78 7.5-6 11a22.35 22.35 0 0 1-4 2z"/><path d="M9 12H4s.55-3.03 2-4c1.62-1.08 5 0 5 0"/><path d="M12 15v5s3.03-.55 4-2c1.08-1.62 0-5 0-5"/>',
  chart: '<path d="M3 3v18h18"/><path d="M7 16v-5"/><path d="M12 16V8"/><path d="M17 16v-3"/>'
}

// 滚动进场指令
const vReveal = {
  mounted(el) {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
    el.classList.add('reveal')
    const io = new IntersectionObserver((entries) => {
      for (const e of entries) {
        if (e.isIntersecting) {
          el.classList.add('in-view')
          io.unobserve(el)
        }
      }
    }, { threshold: 0.1 })
    io.observe(el)
  }
}
</script>

<template>
  <div class="bz-home">
    <!-- ===== Hero ===== -->
    <section class="bz-hero">
      <div class="bz-ambient" aria-hidden="true">
        <span class="bz-orb bz-orb--1"></span>
        <span class="bz-orb bz-orb--2"></span>
        <span class="bz-orb bz-orb--3"></span>
        <div class="bz-grid"></div>
      </div>
      <div class="bz-container bz-hero__inner">
        <div class="bz-hero__copy">
          <span class="bz-badge">Binizox · MIT 开源 · 可私有部署</span>
          <h1 class="bz-hero__title">让知识被智能体<br/><span class="bz-accent">检索、推理与交付</span></h1>
          <p class="bz-hero__subtitle">可私有部署的多租户知识智能体平台</p>
          <p class="bz-hero__desc">
            在一个工作台中统一 RAG、知识图谱、LangGraph 多智能体、MCP/Skills、沙盒工具与权限管理，
            从有来源的回答一直走到可预览、可下载的任务产物。
          </p>
          <div class="bz-hero__actions">
            <a class="bz-btn bz-btn--primary" :href="withBase('/intro/quick-start')">开始部署</a>
            <a v-if="GITHUB" class="bz-btn bz-btn--ghost" :href="GITHUB" target="_blank" rel="noreferrer">查看 GitHub</a>
            <a v-if="DEMO" class="bz-btn bz-btn--text" :href="DEMO" target="_blank" rel="noreferrer">观看演示 →</a>
          </div>
        </div>
        <div class="bz-hero__shot">
          <img
            class="bz-hero__img"
            src="https://xerrors.oss-cn-shanghai.aliyuncs.com/github/image-20260608002434299.png"
            alt="语析 Binizox 产品界面预览"
            loading="eager"
            fetchpriority="high"
          />
        </div>
      </div>
    </section>

    <!-- ===== 数据条 ===== -->
    <section class="bz-stats">
      <div class="bz-container bz-stats__inner">
        <div v-for="s in stats" :key="s.label" class="bz-stat">
          <div class="bz-stat__value">{{ s.value }}</div>
          <div class="bz-stat__label">{{ s.label }}</div>
        </div>
      </div>
    </section>

    <!-- ===== Harness 能力中枢 ===== -->
    <section class="bz-section">
      <div class="bz-container">
        <header v-reveal class="bz-head">
          <span class="bz-head__eyebrow">智能体运行时</span>
          <h2 class="bz-head__title">不止于对话，更能执行与交付</h2>
          <p class="bz-head__sub">Binizox 内置一套完整的 Harness——沙盒、技能、工具、子智能体与中间件，让智能体真正动手完成任务。</p>
        </header>
        <div class="bz-bento">
          <article
            v-for="cap in capabilities"
            :key="cap.title"
            v-reveal
            class="bz-cap"
            :class="{ 'bz-cap--lg': cap.span }"
          >
            <span class="bz-cap__icon" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" v-html="icons[cap.icon]" />
            </span>
            <h3 class="bz-cap__title">{{ cap.title }}</h3>
            <p class="bz-cap__desc">{{ cap.desc }}</p>
            <div class="bz-cap__tags">
              <span v-for="t in cap.tags" :key="t" class="bz-tag">{{ t }}</span>
            </div>
            <img v-if="cap.shot" class="bz-cap__shot-img" :src="cap.shot" :alt="cap.title" loading="lazy" />
          </article>
        </div>
      </div>
    </section>

    <!-- ===== 知识引擎 ===== -->
    <section class="bz-section bz-section--soft">
      <div class="bz-container bz-split">
        <div v-reveal class="bz-split__text">
          <span class="bz-head__eyebrow">知识引擎</span>
          <h2 class="bz-head__title">从文档到可推理的知识资产</h2>
          <ul class="bz-tabs">
            <li
              v-for="(t, i) in engineTabs"
              :key="t.key"
              class="bz-tab"
              :class="{ 'bz-tab--active': activeEngine === i }"
              @click="activeEngine = i"
            >
              <span class="bz-list__ic" aria-hidden="true">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" v-html="icons[t.icon]" />
              </span>
              <div class="bz-tab__body">
                <strong>{{ t.title }}</strong>
                <div class="bz-tab__desc"><p>{{ t.desc }}</p></div>
              </div>
            </li>
          </ul>
        </div>
        <div v-reveal class="bz-split__media">
          <div class="bz-engine-media">
            <Transition name="bz-fade" mode="out-in">
              <img
                v-if="currentEngine.shot"
                :key="currentEngine.key"
                class="bz-engine-frame"
                :src="currentEngine.shot"
                :alt="currentEngine.title"
                loading="lazy"
              />
              <div
                v-else
                :key="currentEngine.key"
                class="bz-engine-frame bz-engine-ph"
                role="img"
                :aria-label="currentEngine.title + ' 预览'"
              >
                <span>{{ currentEngine.title }} · 预览</span>
              </div>
            </Transition>
          </div>
        </div>
      </div>
    </section>

    <!-- ===== 模型供应商墙 ===== -->
    <section class="bz-section">
      <div class="bz-container">
        <header v-reveal class="bz-head">
          <span class="bz-head__eyebrow">模型供应商</span>
          <h2 class="bz-head__title">一处接入，随处切换</h2>
          <p class="bz-head__sub">统一 <code>provider_id:model_id</code> 配置，覆盖主流模型供应商，并支持自定义 provider。</p>
        </header>
        <div v-reveal class="bz-marquee">
          <div class="bz-marquee__row">
            <div class="bz-marquee__track">
              <div v-for="(p, i) in providersTop" :key="'t' + i" class="bz-mq-item">
                <img :src="p.icon" :alt="p.name" loading="lazy" />
                <span>{{ p.name }}</span>
              </div>
            </div>
          </div>
          <div class="bz-marquee__row bz-marquee__row--rev">
            <div class="bz-marquee__track">
              <div v-for="(p, i) in providersBottom" :key="'b' + i" class="bz-mq-item">
                <img :src="p.icon" :alt="p.name" loading="lazy" />
                <span>{{ p.name }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- ===== 工作原理 ===== -->
    <section class="bz-section bz-section--soft">
      <div class="bz-container">
        <header v-reveal class="bz-head">
          <span class="bz-head__eyebrow">工作原理</span>
          <h2 class="bz-head__title">四步搭建你的智能体应用</h2>
        </header>
        <div class="bz-steps">
          <div v-for="(st, i) in steps" :key="st.n" v-reveal class="bz-step">
            <div class="bz-step__n">{{ st.n }}</div>
            <h3 class="bz-step__title">{{ st.title }}</h3>
            <p class="bz-step__desc">{{ st.desc }}</p>
            <span v-if="i < steps.length - 1" class="bz-step__arrow" aria-hidden="true">→</span>
          </div>
        </div>
      </div>
    </section>

    <!-- ===== 产品一览 ===== -->
    <section class="bz-section">
      <div class="bz-container">
        <header v-reveal class="bz-head">
          <span class="bz-head__eyebrow">产品一览</span>
          <h2 class="bz-head__title">一个工作台，覆盖全流程</h2>
        </header>
        <div class="bz-shots">
          <figure v-for="sh in shots" :key="sh.title" v-reveal class="bz-shot">
            <img :src="sh.image" :alt="sh.title" loading="lazy" />
            <figcaption>
              <strong>{{ sh.title }}</strong>
              <span>{{ sh.desc }}</span>
            </figcaption>
          </figure>
        </div>
      </div>
    </section>

    <!-- ===== 企业级 ===== -->
    <section class="bz-section bz-section--soft">
      <div class="bz-container">
        <header v-reveal class="bz-head">
          <span class="bz-head__eyebrow">企业级与可集成</span>
          <h2 class="bz-head__title">从原型验证到团队落地</h2>
        </header>
        <div class="bz-cards3">
          <article v-for="e in enterprise" :key="e.title" v-reveal class="bz-card">
            <span class="bz-cap__icon" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" v-html="icons[e.icon]" />
            </span>
            <h3>{{ e.title }}</h3>
            <p>{{ e.desc }}</p>
          </article>
        </div>
      </div>
    </section>

    <!-- ===== 应用场景 ===== -->
    <section class="bz-section">
      <div class="bz-container">
        <header v-reveal class="bz-head">
          <span class="bz-head__eyebrow">应用场景</span>
          <h2 class="bz-head__title">适配你的真实业务</h2>
        </header>
        <div class="bz-cards3">
          <article v-for="c in cases" :key="c.title" v-reveal class="bz-card bz-card--case">
            <h3>{{ c.title }}</h3>
            <p>{{ c.desc }}</p>
          </article>
        </div>
      </div>
    </section>

    <!-- ===== 技术栈 ===== -->
    <section class="bz-section bz-section--soft">
      <div class="bz-container">
        <header v-reveal class="bz-head">
          <span class="bz-head__eyebrow">技术栈</span>
          <h2 class="bz-head__title">现代而稳健的工程基座</h2>
        </header>
        <div class="bz-tech">
          <div v-for="t in techStack" :key="t.group" v-reveal class="bz-tech__row">
            <div class="bz-tech__group">{{ t.group }}</div>
            <div class="bz-tech__items">
              <span v-for="it in t.items" :key="it" class="bz-chip">{{ it }}</span>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- ===== 快速开始 ===== -->
    <section class="bz-section">
      <div class="bz-container">
        <header v-reveal class="bz-head">
          <span class="bz-head__eyebrow">快速开始</span>
          <h2 class="bz-head__title">三步本地跑起来</h2>
        </header>
        <div v-reveal class="bz-quick">
          <pre class="bz-code"><code><span class="bz-c-cmt"># 1. 克隆并初始化</span>
git clone &lt;your-binizox-repository-url&gt; Binizox
cd Binizox && ./scripts/init.sh

<span class="bz-c-cmt"># 2. 使用 Docker 启动</span>
docker compose up --build

<span class="bz-c-cmt"># 3. 浏览器访问</span>
open http://localhost:5173</code></pre>
          <p class="bz-quick__tip">无需知识库 / 知识图谱等重依赖时，可用 <code>make up-lite</code> 以 LITE 轻量模式快速启动。</p>
        </div>
      </div>
    </section>

    <!-- ===== 贡献者 & 致谢 ===== -->
    <section class="bz-section bz-section--soft">
      <div class="bz-container bz-center">
        <header v-reveal class="bz-head">
          <span class="bz-head__eyebrow">社区</span>
          <h2 class="bz-head__title">由开源社区共同构建</h2>
        </header>
        <a v-if="GITHUB" v-reveal :href="GITHUB + '/graphs/contributors'" target="_blank" rel="noreferrer" class="bz-contrib">
          查看 Binizox 贡献者
        </a>
        <p v-reveal class="bz-credits">
          站在巨人的肩上 ——
          <template v-for="(c, i) in credits" :key="c.name">
            <a :href="c.url" target="_blank" rel="noreferrer">{{ c.name }}</a><span v-if="i < credits.length - 1"> · </span>
          </template>
        </p>
      </div>
    </section>

    <!-- ===== 最终 CTA ===== -->
    <section class="bz-cta">
      <div class="bz-container bz-cta__inner" v-reveal>
        <h2>把知识接入真正能执行的智能体</h2>
        <p>从 LITE 模式快速体验，再按需启用完整知识库与知识图谱能力。</p>
        <div class="bz-hero__actions bz-cta__actions">
          <a class="bz-btn bz-btn--primary" :href="withBase('/intro/quick-start')">快速开始</a>
          <a v-if="GITHUB" class="bz-btn bz-btn--ghost" :href="GITHUB" target="_blank" rel="noreferrer">前往 GitHub ★</a>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.bz-home {
  --bz-max: 1152px;
  --bz-gap: 24px;
  --bz-brand: var(--main-700);
  --bz-brand-hover: var(--main-bright);
  --bz-brand-soft: rgba(4, 106, 130, .12);
  --bz-lime: #c6f43a;
  --bz-lime-strong: #6f9300;
  --bz-lime-soft: rgba(198, 244, 58, .24);
  color: var(--vp-c-text-1);
  font-size: 16px;
  line-height: 1.6;
}
.bz-container {
  max-width: var(--bz-max);
  margin: 0 auto;
  padding: 0 24px;
}
.bz-center { text-align: center; }
.bz-accent { color: var(--bz-brand); }

/* 段落节奏 */
.bz-section { padding: 96px 0; }
.bz-section--soft { background: var(--vp-c-bg-soft); }

/* 标题块 */
.bz-head { max-width: 720px; margin: 0 auto 48px; text-align: center; }
.bz-head__eyebrow {
  display: inline-block;
  font-size: 13px;
  font-weight: 600;
  letter-spacing: .08em;
  text-transform: uppercase;
  color: var(--bz-brand);
  margin-bottom: 12px;
}
.bz-head__title { font-size: 34px; font-weight: 700; line-height: 1.25; margin: 0; letter-spacing: -.01em; }
.bz-head__sub { margin: 16px auto 0; color: var(--vp-c-text-2); font-size: 17px; }
.bz-head__sub code, .bz-quick__tip code {
  font-size: .85em; padding: 2px 6px; border-radius: 6px;
  background: var(--vp-c-bg-alt); color: var(--bz-brand);
}

/* ===== Hero ===== */
.bz-hero { padding: 88px 0 72px; position: relative; overflow: hidden; }
.bz-hero__inner {
  position: relative; z-index: 1;
  display: grid; grid-template-columns: .82fr 1.18fr; gap: 56px; align-items: center;
}
.bz-hero__copy { min-width: 0; }

/* 氛围背景：浮动光球 + 网格 mesh */
.bz-ambient { position: absolute; inset: 0; z-index: 0; overflow: hidden; pointer-events: none; }
.bz-orb { position: absolute; border-radius: 50%; filter: blur(70px); will-change: transform; }
.bz-orb--1 {
  width: 460px; height: 460px; top: -180px; right: -80px;
  background: var(--bz-brand-soft); opacity: .6;
  animation: yxOrbFloat 18s ease-in-out infinite;
}
.bz-orb--2 {
  width: 380px; height: 380px; top: -120px; left: -120px;
  background: var(--bz-lime-soft); opacity: .5;
  animation: yxOrbFloat 22s ease-in-out infinite reverse;
}
.bz-orb--3 {
  width: 320px; height: 320px; top: 30px; left: 46%;
  background: var(--bz-brand-soft); opacity: .5;
  animation: yxOrbFloat 26s ease-in-out infinite;
}
.bz-grid {
  position: absolute; inset: 0;
  background-image:
    linear-gradient(to right, var(--vp-c-divider) 1px, transparent 1px),
    linear-gradient(to bottom, var(--vp-c-divider) 1px, transparent 1px);
  background-size: 60px 60px; opacity: .5;
  -webkit-mask-image: radial-gradient(ellipse 75% 60% at 50% 0%, #000, transparent 72%);
  mask-image: radial-gradient(ellipse 75% 60% at 50% 0%, #000, transparent 72%);
}
@keyframes yxOrbFloat {
  0%, 100% { transform: translate(0, 0) scale(1); }
  50% { transform: translate(0, -26px) scale(1.04); }
}
.bz-badge {
  display: inline-block; font-size: 13px; font-weight: 500;
  padding: 6px 14px; border-radius: 999px;
  border: 1px solid var(--vp-c-divider);
  background: var(--vp-c-bg); color: var(--vp-c-text-2);
  margin-bottom: 24px;
}
.bz-hero__title { font-size: 52px; font-weight: 800; line-height: 1.08; margin: 0; letter-spacing: -.04em; text-wrap: balance; }
.bz-hero__subtitle { font-size: 22px; font-weight: 650; margin: 22px 0 0; color: var(--vp-c-text-1); }
.bz-hero__desc { max-width: 620px; margin: 16px 0 0; color: var(--vp-c-text-2); font-size: 17px; text-wrap: pretty; }
.bz-hero__actions { display: flex; flex-wrap: wrap; gap: 14px; justify-content: flex-start; margin-top: 30px; }

/* 按钮 */
.bz-btn {
  display: inline-flex; align-items: center; gap: 6px;
  height: 44px; padding: 0 22px; border-radius: 10px;
  font-size: 15px; font-weight: 600; cursor: pointer;
  transition: transform .2s ease, background-color .2s ease, border-color .2s ease, color .2s ease;
  border: 1px solid transparent; text-decoration: none;
}
.bz-btn--primary { background: var(--bz-brand); color: #fff; }
.bz-btn--primary:hover { background: var(--bz-brand-hover); transform: translateY(-1px); }
.bz-btn--ghost { border-color: var(--vp-c-divider); color: var(--vp-c-text-1); background: var(--vp-c-bg); }
.bz-btn--ghost:hover { border-color: var(--bz-brand); color: var(--bz-brand); }
.bz-btn--text { color: var(--vp-c-text-2); }
.bz-btn--text:hover { color: var(--bz-brand); }

.bz-hero__shot { margin-top: 0; }
.bz-hero__img {
  display: block; width: 100%; border-radius: 16px;
  border: 1px solid var(--vp-c-divider);
  box-shadow: 0 28px 72px rgba(2, 57, 68, .18);
}

/* 占位图 */
.bz-placeholder {
  aspect-ratio: 16 / 9; width: 100%;
  display: flex; align-items: center; justify-content: center;
  border: 1px dashed var(--vp-c-divider); border-radius: 14px;
  background:
    linear-gradient(var(--vp-c-bg-soft), var(--vp-c-bg-soft)) padding-box,
    var(--vp-c-bg);
  color: var(--vp-c-text-3); font-size: 14px; letter-spacing: .02em;
}
.bz-placeholder--hero {
  border-style: solid;
  box-shadow: 0 24px 60px -28px rgba(0, 0, 0, .25);
}

/* ===== 数据条 ===== */
.bz-stats { border-top: 1px solid var(--vp-c-divider); border-bottom: 1px solid var(--vp-c-divider); }
.bz-stats__inner { display: grid; grid-template-columns: repeat(4, 1fr); }
.bz-stat { text-align: center; padding: 32px 16px; }
.bz-stat + .bz-stat { border-left: 1px solid var(--vp-c-divider); }
.bz-stat__value {
  font-size: 36px; font-weight: 800; color: var(--bz-brand);
  font-variant-numeric: tabular-nums; letter-spacing: -.02em;
}
.bz-stat__label { margin-top: 6px; font-size: 14px; color: var(--vp-c-text-2); }

/* ===== Bento ===== */
.bz-bento {
  display: grid; gap: var(--bz-gap);
  grid-template-columns: repeat(3, 1fr);
}
.bz-cap {
  border: 1px solid var(--vp-c-divider); border-radius: 16px;
  padding: 28px; background: var(--vp-c-bg);
  transition: transform .2s ease, border-color .2s ease;
}
.bz-cap:hover { transform: translateY(-3px); border-color: var(--bz-brand); }
.bz-cap--lg { grid-column: span 1; grid-row: span 2; display: flex; flex-direction: column; }
.bz-cap__icon {
  display: inline-flex; align-items: center; justify-content: center;
  width: 44px; height: 44px; border-radius: 12px;
  background: var(--bz-brand-soft); color: var(--bz-brand);
  margin-bottom: 18px;
}
.bz-cap__icon svg { width: 22px; height: 22px; }
.bz-cap__title { font-size: 18px; font-weight: 700; margin: 0 0 8px; }
.bz-cap__desc { color: var(--vp-c-text-2); font-size: 14.5px; margin: 0; }
.bz-cap__tags { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 16px; }
.bz-tag {
  font-size: 12px; padding: 3px 10px; border-radius: 999px;
  background: var(--vp-c-bg-soft); border: 1px solid var(--vp-c-divider);
  color: var(--vp-c-text-2);
}
.bz-cap__shot-img {
  display: block; width: 100%; margin-top: 20px;
  border-radius: 12px; border: 1px solid var(--vp-c-divider);
}

/* ===== Split（知识引擎）===== */
.bz-split { display: grid; grid-template-columns: 0.82fr 1.18fr; gap: 48px; align-items: start; }
.bz-split .bz-head__eyebrow { display: inline-block; }
.bz-split .bz-head__title { text-align: left; font-size: 30px; }
.bz-tabs { list-style: none; margin: 28px 0 0; padding: 0; display: grid; gap: 8px; }
.bz-tab {
  display: flex; align-items: center; gap: 14px; padding: 12px 14px;
  border-radius: 12px; border: 1px solid transparent; cursor: pointer;
  transition: background-color .2s ease, border-color .2s ease;
}
.bz-tab:hover { background: var(--vp-c-bg); }
.bz-tab--active { background: var(--vp-c-bg); border-color: var(--vp-c-divider); }
.bz-tab .bz-list__ic { opacity: .55; transition: opacity .2s ease; }
.bz-tab--active .bz-list__ic { opacity: 1; }
.bz-list__ic {
  flex: none; width: 38px; height: 38px; border-radius: 10px;
  display: inline-flex; align-items: center; justify-content: center;
  background: var(--bz-brand-soft); color: var(--bz-brand);
}
.bz-list__ic svg { width: 20px; height: 20px; }
.bz-tab--active .bz-list__ic { background: var(--bz-lime-soft); color: var(--bz-lime-strong); }
.bz-tab__body { min-width: 0; }
.bz-tab strong { display: block; font-size: 16px; }
.bz-tab__desc {
  display: grid; grid-template-rows: 0fr;
  transition: grid-template-rows .25s ease;
}
.bz-tab--active .bz-tab__desc { grid-template-rows: 1fr; }
.bz-tab__desc p {
  overflow: hidden; margin: 0; color: var(--vp-c-text-2); font-size: 14px; line-height: 1.55;
}
.bz-tab--active .bz-tab__desc p { margin-top: 4px; }

/* 知识引擎媒体区（4:3，随 tab 切换） */
.bz-engine-media {
  position: relative; width: 100%; aspect-ratio: 4 / 3; margin-top: 40px;
  border-radius: 14px; overflow: hidden; border: 1px solid var(--vp-c-divider);
}
.bz-engine-frame { position: absolute; inset: 0; width: 100%; height: 100%; display: block; }
img.bz-engine-frame { object-fit: cover; }
.bz-engine-ph {
  display: flex; align-items: center; justify-content: center;
  background: var(--vp-c-bg-soft); color: var(--vp-c-text-3);
  font-size: 14px; letter-spacing: .02em;
}
.bz-fade-enter-active, .bz-fade-leave-active { transition: opacity .25s ease; }
.bz-fade-enter-from, .bz-fade-leave-to { opacity: 0; }

/* ===== 模型供应商墙（跑马灯）===== */
.bz-marquee {
  display: flex; flex-direction: column; gap: 18px;
  -webkit-mask-image: linear-gradient(90deg, transparent, #000 8%, #000 92%, transparent);
  mask-image: linear-gradient(90deg, transparent, #000 8%, #000 92%, transparent);
}
.bz-marquee__row { display: flex; overflow: hidden; }
.bz-marquee__track {
  display: flex; gap: 16px; flex: none; width: max-content;
  padding-right: 16px;
  animation: yxMarquee 42s linear infinite;
}
.bz-marquee__row--rev .bz-marquee__track { animation-direction: reverse; }
.bz-marquee:hover .bz-marquee__track { animation-play-state: paused; }
.bz-mq-item {
  display: flex; align-items: center; gap: 10px; flex: none;
  padding: 10px 20px; border-radius: 999px;
  border: 1px solid var(--vp-c-divider); background: var(--vp-c-bg);
  white-space: nowrap;
}
.bz-mq-item img { width: 24px; height: 24px; object-fit: contain; flex: none; }
.bz-mq-item span { font-weight: 600; font-size: 15px; color: var(--vp-c-text-1); }
@keyframes yxMarquee {
  from { transform: translateX(0); }
  to { transform: translateX(-50%); }
}

/* ===== 工作原理 ===== */
.bz-steps { display: grid; grid-template-columns: repeat(4, 1fr); gap: var(--bz-gap); }
.bz-step { position: relative; padding: 28px 24px; border: 1px solid var(--vp-c-divider); border-radius: 16px; background: var(--vp-c-bg); }
.bz-step__n { font-size: 26px; font-weight: 800; color: var(--bz-brand); font-variant-numeric: tabular-nums; }
.bz-step__title { font-size: 17px; font-weight: 700; margin: 10px 0 8px; }
.bz-step__desc { margin: 0; color: var(--vp-c-text-2); font-size: 14px; }
.bz-step__arrow {
  position: absolute; right: -16px; top: 50%; transform: translateY(-50%);
  color: var(--vp-c-text-3); font-size: 18px; z-index: 1;
}

/* ===== 产品一览 ===== */
.bz-shots { display: grid; grid-template-columns: repeat(2, 1fr); gap: 32px; }
.bz-shot { margin: 0; }
.bz-shot > img {
  display: block; width: 100%; aspect-ratio: 16 / 9; object-fit: cover;
  border-radius: 14px; border: 1px solid var(--vp-c-divider); background: var(--vp-c-bg-soft);
}
.bz-shot figcaption { margin-top: 14px; }
.bz-shot figcaption strong { font-size: 16px; }
.bz-shot figcaption span { display: block; color: var(--vp-c-text-2); font-size: 14px; margin-top: 2px; }

/* ===== 三卡（企业级 / 场景）===== */
.bz-cards3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: var(--bz-gap); }
.bz-card {
  border: 1px solid var(--vp-c-divider); border-radius: 16px;
  padding: 28px; background: var(--vp-c-bg);
  transition: transform .2s ease, border-color .2s ease;
}
.bz-card:hover { transform: translateY(-3px); border-color: var(--bz-brand); }
.bz-card h3 { font-size: 18px; font-weight: 700; margin: 0 0 8px; }
.bz-card p { margin: 0; color: var(--vp-c-text-2); font-size: 14.5px; }
.bz-card--case { border-left: 3px solid var(--bz-lime); }

/* ===== 技术栈 ===== */
.bz-tech { max-width: 860px; margin: 0 auto; }
.bz-tech__row { display: grid; grid-template-columns: 100px 1fr; gap: 24px; align-items: center; padding: 18px 0; }
.bz-tech__row + .bz-tech__row { border-top: 1px solid var(--vp-c-divider); }
.bz-tech__group { font-weight: 600; color: var(--vp-c-text-2); font-size: 14px; }
.bz-tech__items { display: flex; flex-wrap: wrap; gap: 10px; }
.bz-chip {
  font-size: 14px; font-weight: 500; padding: 6px 14px; border-radius: 8px;
  background: var(--vp-c-bg-soft); border: 1px solid var(--vp-c-divider);
}

/* ===== 快速开始 ===== */
.bz-quick { max-width: 760px; margin: 0 auto; }
.bz-code {
  margin: 0; padding: 24px; border-radius: 14px;
  background: #1b1b1f;
  border: 1px solid var(--vp-c-divider);
  overflow-x: auto; font-size: 14px; line-height: 1.8;
  font-family: var(--vp-font-family-mono);
  color: #e6e6e6;
}
.bz-c-cmt { color: #6a9955; }
.bz-quick__tip { margin: 18px 0 0; text-align: center; color: var(--vp-c-text-2); font-size: 14px; }

/* ===== 社区 ===== */
.bz-contrib { display: block; max-width: 720px; margin: 0 auto; }
.bz-contrib img { width: 100%; border-radius: 12px; }
.bz-credits { margin: 32px 0 0; color: var(--vp-c-text-2); font-size: 14.5px; }
.bz-credits a { color: var(--bz-brand); text-decoration: none; }
.bz-credits a:hover { text-decoration: underline; }

/* ===== 最终 CTA ===== */
.bz-cta { padding: 96px 0; text-align: center; border-top: 1px solid var(--vp-c-divider); }
.bz-cta__inner h2 { font-size: 34px; font-weight: 800; margin: 0; letter-spacing: -.01em; }
.bz-cta__inner p { margin: 14px 0 0; color: var(--vp-c-text-2); font-size: 17px; }
.bz-cta__actions { justify-content: center; margin-top: 28px; }

/* ===== 进场动画 ===== */
.reveal { opacity: 0; transform: translateY(18px); transition: opacity .6s ease, transform .6s ease; }
.reveal.in-view { opacity: 1; transform: none; }

/* ===== 响应式 ===== */
@media (max-width: 1024px) {
  .bz-hero__inner { grid-template-columns: 1fr; gap: 48px; }
  .bz-bento { grid-template-columns: repeat(2, 1fr); }
  .bz-cap--lg { grid-column: span 2; grid-row: auto; }
}
@media (max-width: 768px) {
  .bz-section, .bz-hero, .bz-cta { padding: 64px 0; }
  .bz-hero { padding-top: 64px; }
  .bz-hero__inner { gap: 40px; }
  .bz-hero__title { font-size: 44px; }
  .bz-hero__subtitle { font-size: 20px; }
  .bz-head__title { font-size: 28px; }
  .bz-bento, .bz-cards3, .bz-steps, .bz-shots { grid-template-columns: 1fr; }
  .bz-cap--lg { grid-column: auto; }
  .bz-split { grid-template-columns: 1fr; gap: 32px; }
  .bz-split .bz-head__title { text-align: center; }
  .bz-split__text { text-align: center; }
  .bz-tab { text-align: left; }
  .bz-stats__inner { grid-template-columns: repeat(2, 1fr); }
  .bz-stat:nth-child(3) { border-left: none; }
  .bz-stat:nth-child(odd) { border-left: none; }
  .bz-stat:nth-child(even) { border-left: 1px solid var(--vp-c-divider); }
  .bz-stat:nth-child(n+3) { border-top: 1px solid var(--vp-c-divider); }
  .bz-step__arrow { display: none; }
}
@media (prefers-reduced-motion: reduce) {
  .reveal { opacity: 1; transform: none; transition: none; }
  .bz-btn:hover, .bz-cap:hover, .bz-card:hover, .bz-provider:hover { transform: none; }
  .bz-orb, .bz-marquee__track { animation: none; }
}
</style>
