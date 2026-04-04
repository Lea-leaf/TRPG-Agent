<script setup lang="ts">
import { ref } from 'vue'

const SESSION_STORAGE_KEY = 'trpg-chat-session-id'

const getStoredSessionId = (): string | null => {
  const value = localStorage.getItem(SESSION_STORAGE_KEY)
  return value && value.trim() ? value : null
}

const setStoredSessionId = (sessionId: string) => {
  localStorage.setItem(SESSION_STORAGE_KEY, sessionId)
}

type ChatMessage = {
  role: 'user' | 'assistant'
  content: string
}

type PendingAction = {
  type: string
  reason?: string
  formula?: string
}

type ChatResponsePayload = {
  reply?: string
  plan?: string | null
  session_id?: string
  pending_action?: PendingAction | null
}

const inputText = ref('')
const isSending = ref(false)
const errorText = ref('')
const sessionId = ref<string | null>(getStoredSessionId())
const pendingAction = ref<PendingAction | null>(null)
const messages = ref<ChatMessage[]>([
  { role: 'assistant', content: '你好，我是 TRPG 助手。你可以直接开始提问。' }
])

const sendMessage = async (action?: string | Event) => {
  const isActionStr = typeof action === 'string'
  const actionValue = isActionStr ? action : undefined
  const text = inputText.value.trim()
  
  // 只在没有 action 且没有 text 时拦截
  if (!isActionStr && !text) return
  if (isSending.value) return

  errorText.value = ''
  
  if (!isActionStr && text) {
    messages.value.push({ role: 'user', content: text })
    inputText.value = ''
  } else if (isActionStr && actionValue === 'confirmed' && pendingAction.value) {
    messages.value.push({ role: 'user', content: `[掷骰确认: ${pendingAction.value.reason || '无'}]` })
  }

  isSending.value = true

  try {
    const payload = isActionStr 
      ? { session_id: sessionId.value, resume_action: actionValue }
      : { message: text, session_id: sessionId.value }
      
    const response = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }

    const data = (await response.json()) as ChatResponsePayload
    if (data.session_id && data.session_id !== sessionId.value) {
      sessionId.value = data.session_id
      setStoredSessionId(data.session_id)
    }
    
    pendingAction.value = data.pending_action || null
    
    const reply = String(data.reply ?? '').trim()
    if (reply) {
      messages.value.push({ role: 'assistant', content: reply })
    } else if (!pendingAction.value && !reply) {
      messages.value.push({ role: 'assistant', content: '模型没有返回内容。' })
    }
  } catch (error) {
    errorText.value = '发送失败，请检查后端服务和模型配置。'
    console.error(error)
  } finally {
    isSending.value = false
  }
}
</script>

<template>
  <main class="chat-page">
    <section class="chat-panel">
      <header class="chat-header">
        <h1>TRPG 对话测试</h1>
      </header>

      <div class="message-list">
        <article
          v-for="(message, index) in messages"
          :key="index"
          :class="['message-item', message.role]"
        >
          <p class="message-role">{{ message.role === 'user' ? '你' : 'AI' }}</p>
          <p class="message-content">{{ message.content }}</p>
        </article>
      </div>

      <p v-if="errorText" class="error-text">{{ errorText }}</p>

      <div v-if="pendingAction?.type === 'dice_roll'" class="action-panel">
        <p><strong>动作挂起：判断需要掷骰</strong></p>
        <p>原因：{{ pendingAction.reason }} ({{ pendingAction.formula }})</p>
        <button class="roll-btn" @click="sendMessage('confirmed')" :disabled="isSending">
          确认掷骰
        </button>
      </div>

      <form class="input-row" @submit.prevent="sendMessage()">
        <input
          v-model="inputText"
          type="text"
          placeholder="输入内容并回车发送..."
          :disabled="isSending || pendingAction !== null"
        />
        <button type="submit" :disabled="isSending || (!inputText.trim() && !pendingAction)">
          {{ isSending ? '发送中...' : '发送' }}
        </button>
      </form>
    </section>
  </main>
</template>

<style scoped>
.chat-page {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 24px;
  box-sizing: border-box;
}

.chat-panel {
  width: 100%;
  max-width: 780px;
  border: 1px solid #2f2f2f;
  border-radius: 12px;
  padding: 16px;
  box-sizing: border-box;
}

.chat-header h1 {
  margin: 0 0 12px;
  font-size: 22px;
}

.message-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: 58vh;
  overflow-y: auto;
  padding: 8px 4px;
}

.message-item {
  border-radius: 10px;
  padding: 10px 12px;
}

.message-item.user {
  background: rgba(66, 184, 131, 0.2);
}

.message-item.assistant {
  background: rgba(140, 140, 255, 0.15);
}

.message-role {
  font-size: 12px;
  opacity: 0.8;
  margin-bottom: 4px;
}

.message-content {
  white-space: pre-wrap;
  line-height: 1.5;
}

.input-row {
  display: flex;
  gap: 10px;
  margin-top: 12px;
}

.input-row input {
  flex: 1;
  height: 40px;
  border-radius: 8px;
  border: 1px solid #3f3f3f;
  padding: 0 12px;
}

.input-row button {
  min-width: 96px;
  border: none;
  border-radius: 8px;
  background: #42b883;
  color: #fff;
  cursor: pointer;
}

.input-row button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.action-panel {
  margin-top: 10px;
  padding: 12px;
  background: rgba(255, 165, 0, 0.15);
  border: 1px solid #ffaf40;
  border-radius: 8px;
  text-align: center;
}

.action-panel p {
  margin: 4px 0;
  font-size: 14px;
}

.roll-btn {
  margin-top: 8px;
  padding: 8px 24px;
  background: #ffaf40;
  color: white;
  border: none;
  border-radius: 6px;
  cursor: pointer;
  font-weight: bold;
}

.roll-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.error-text {
  color: #ff6b6b;
  margin-top: 10px;
}
</style>