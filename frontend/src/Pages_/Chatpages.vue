<!-- frontend/src/Pages_/ChatPage.vue -->
<template>
  <div class="chat-page" ref="containerRef">
    <!-- 左侧聊天区 -->
    <div
      class="chat-main"
      :class="{ hidden: rightWidth === 100 }"
      :style="{ '--chat-font-scale': String(appSettings.fontScale) }"
    >
      <div class="chat-container">
        <header class="chat-header">
          <h1>TRPG 助手</h1>
          <div class="header-actions">
            <button
              class="session-action-btn"
              :disabled="isSending"
              @click="startNewSession"
              title="创建新会话"
            >
              <Plus :size="16" />
            </button>
            <button
              class="session-action-btn danger"
              :disabled="isSending || !sessionId"
              @click="deleteCurrentSession"
              title="删除当前会话"
            >
              <Trash2 :size="16" />
            </button>
            <button
              class="debug-toggle"
              :class="{ active: debugMode }"
              @click="toggleDebugMode"
              title="调试模式"
            >
              🔧
            </button>
          </div>
        </header>

        <div class="message-list" ref="messageListRef" @scroll="handleScroll">
          <ChatMessage
            v-for="msg in messages"
            :key="msg.id"
            :message="msg"
            :scroll-to-bottom="scrollToBottom"
            @firstChar="stopLoading"
          />
        </div>

        <p v-if="errorText" class="error-text">{{ errorText }}</p>

        <ActionPanel
          :pending-action="pendingAction"
          :disabled="isSending"
          @confirm="confirmDiceRoll"
          @revive="respondToPlayerDeath('revive')"
          @end-combat="respondToPlayerDeath('end')"
          @react="respondToReaction"
          @skip-reaction="respondToReaction(null)"
        />

        <div v-if="showNextTurnBtn" class="next-turn-bar">
          <button
            class="next-turn-btn"
            :disabled="isSending"
            @click="sendTextMessage('我结束回合')"
          >
            结束回合 →
          </button>
        </div>

        <ChatInput
          :disabled="isSending || pendingAction !== null"
          button-text="发送"
          placeholder="输入内容并回车发送..."
          @send="sendTextMessage"
        />
      </div>
    </div>

    <!-- 拖拽条 -->
    <div
      v-if="rightWidth > 0 && rightWidth < 100"
      class="resize-handle"
      @mousedown="startDrag"
    ></div>

    <!-- 右侧功能区 -->
    <div class="function-area" :style="{ width: rightWidth + '%' }">
      <CharacterSidebar
        ref="characterSidebarRef"
        :external-player="playerState"
        :combat="combatState"
        :space="spaceState"
        :scene-units="sceneUnitsState"
      />
    </div>

    <!-- 圆形控制按钮 -->
    <Transition name="fade">
      <button
        v-if="showToggleBtn"
        class="toggle-btn"
        :class="{ rotated: rightWidth === 0 }"
        @click="togglePanel"
      >
        {{ rightWidth === 0 ? '◀' : '▶' }}
      </button>
    </Transition>

    <Dice3D v-if="showDiceAnimation" ref="dice3dRef" class="chat-dice-overlay" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, provide, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { Plus, Trash2 } from 'lucide-vue-next'
import ChatMessage from '../components/Chat/ChatMessage.vue'
import ChatInput from '../components/Chat/ChatInput.vue'
import ActionPanel from '../components/Chat/ActionPanel.vue'
import CharacterSidebar from '../components/Chat/SideCharacterPanel/CharacterSidebar.vue'
import Dice3D from '../components/Dice3D/Dice3D.vue'
import { useChatSession } from '../composables/useChatSession'
import { useChatMessages } from '../composables/useChatMessages'
import { useChatSender } from '../composables/useChatSender'
import { chatService } from '../Services_/chatService'
import { createSession, deleteSession as deleteSessionApi } from '../Services_/sessionService'
import { APP_SETTINGS_UPDATED_EVENT, loadAppSettings, type AppSettings } from '../Services_/SettingsPageService'

import '../styles_/Chatpages.css'

// 右侧面板状态
const containerRef = ref<HTMLElement | null>(null)
const messageListRef = ref<HTMLElement | null>(null)
const dice3dRef = ref<InstanceType<typeof Dice3D> | null>(null)
const characterSidebarRef = ref<InstanceType<typeof CharacterSidebar> | null>(null)
const showDiceAnimation = ref(false)
const rightWidth = ref(25)
const showToggleBtn = ref(false)
const isDragging = ref(false)
const appSettings = ref(loadAppSettings())

// 聊天逻辑
const { sessionId, updateSessionId, clearSessionId } = useChatSession()
const {
  messages,
  pendingAction,
  errorText,
  isSending,
  combatState,
  spaceState,
  sceneUnitsState,
  playerState,
  debugMode,
  addUserMessage,
  addAssistantMessage,
  addCombatMessage,
  addToolMessage,
  addConfirmedMessage,
  setPendingAction,
  setPlayerState,
  setCombatState,
  setSpaceState,
  setSceneUnitsState,
  setError,
  setSending,
  clearError,
  setMessages,
  resetChatState,
  toggleDebugMode,
  startLoading,
  stopLoading,
} = useChatMessages(appSettings.value.defaultDebugMode)

// 通过 provide 向子组件注入 debugMode
provide('debugMode', debugMode)
provide('skipOutputAnimation', computed(() => appSettings.value.skipOutputAnimation))

// 战斗开始时优先切到血量概览，结束后回到角色页
watch(combatState, (hasCombat) => {
  if (characterSidebarRef.value) {
    if (hasCombat) {
      characterSidebarRef.value.setViewMode('hp')
    } else {
      characterSidebarRef.value.setViewMode('character')
    }
  }
}, { immediate: true })

const handleDiceRollAnim = async (rawRoll: number) => {
  showDiceAnimation.value = true
  await nextTick()
  if (dice3dRef.value) {
    await dice3dRef.value.throwDice(rawRoll)
    await new Promise((resolve) => setTimeout(resolve, 1500))
  }
  showDiceAnimation.value = false
}

const { sendTextMessage, confirmDiceRoll, respondToPlayerDeath, respondToReaction } = useChatSender(
  sessionId,
  updateSessionId,
  addUserMessage,
  addAssistantMessage,
  addCombatMessage,
  addToolMessage,
  addConfirmedMessage,
  setPendingAction,
  setPlayerState,
  setCombatState,
  setSpaceState,
  setSceneUnitsState,
  setError,
  setSending,
  clearError,
  pendingAction,
  handleDiceRollAnim,
  startLoading,
  stopLoading
)

const showNextTurnBtn = computed(() => {
  if (!combatState.value || pendingAction.value) return false
  const currentActorId: string = combatState.value.current_actor_id || ''
  return currentActorId.startsWith('player_')
})

const autoScrollDisabled = ref(!appSettings.value.autoScrollChat)

const isNearBottom = (): boolean => {
  const el = messageListRef.value
  if (!el) return true
  const threshold = 50
  return el.scrollHeight - el.scrollTop - el.clientHeight < threshold
}

const handleScroll = () => {
  if (!appSettings.value.autoScrollChat) {
    autoScrollDisabled.value = true
    return
  }
  autoScrollDisabled.value = !isNearBottom()
}

const scrollToBottom = () => {
  nextTick(() => {
    if (!appSettings.value.autoScrollChat) return
    if (!autoScrollDisabled.value && messageListRef.value) {
      messageListRef.value.scrollTop = messageListRef.value.scrollHeight
    }
  })
}

// 监听消息变化自动滚动
watch(messages, scrollToBottom, { deep: true })

const hydrateCurrentSession = async () => {
  if (!sessionId.value) return

  try {
    const history = await chatService.fetchHistory(sessionId.value)
    const shouldHydrateMessages = messages.value.length === 1
      && messages.value[0]?.role === 'assistant'
      && messages.value[0]?.content === '你好，我是 TRPG 助手。你可以直接开始提问。'

    if (history.messages.length > 0 && shouldHydrateMessages) {
      setMessages(history.messages.map(m => ({
        id: crypto.randomUUID(),
        role: m.role as 'user' | 'assistant',
        content: m.content,
        timestamp: Date.now(),
      })))
    }
    if (history.player) setPlayerState(history.player)
    if (history.combat) setCombatState(history.combat)
    if ((history as any).space) setSpaceState((history as any).space)
    if ((history as any).scene_units) setSceneUnitsState((history as any).scene_units)
  } catch {
    clearSessionId()
  }
}

const startNewSession = async () => {
  try {
    const session = await createSession()
    updateSessionId(session.id)
    resetChatState()
    clearError()
  } catch (error) {
    setError(error instanceof Error ? error.message : '创建会话失败')
  }
}

const deleteCurrentSession = async () => {
  if (!sessionId.value || !confirm('确定要删除当前会话吗？相关记忆和 trace 会一起清理。')) return

  try {
    await deleteSessionApi(sessionId.value)
    clearSessionId()
    resetChatState()
    clearError()
  } catch (error) {
    setError(error instanceof Error ? error.message : '删除会话失败')
  }
}

onMounted(async () => {
  document.addEventListener('mousemove', handleMouseMove)
  window.addEventListener('storage', handleSettingsStorage)
  window.addEventListener(APP_SETTINGS_UPDATED_EVENT, handleSettingsUpdated as EventListener)

  const pendingSessionId = sessionStorage.getItem('pending_session_id')
  if (pendingSessionId) {
    updateSessionId(pendingSessionId)
    sessionStorage.removeItem('pending_session_id')
  }

  await hydrateCurrentSession()
})

onUnmounted(() => {
  document.removeEventListener('mousemove', handleMouseMove)
  window.removeEventListener('storage', handleSettingsStorage)
  window.removeEventListener(APP_SETTINGS_UPDATED_EVENT, handleSettingsUpdated as EventListener)
})

const handleSettingsStorage = (event: StorageEvent) => {
  if (event.key !== 'trpg-app-settings') return
  applySettings(loadAppSettings())
}

const handleSettingsUpdated = (event: CustomEvent<AppSettings>) => {
  applySettings(event.detail)
}

const applySettings = (settings: AppSettings) => {
  appSettings.value = settings
  debugMode.value = settings.defaultDebugMode
  autoScrollDisabled.value = !settings.autoScrollChat
  if (settings.autoScrollChat) {
    scrollToBottom()
  }
}

const togglePanel = () => {
  rightWidth.value = rightWidth.value === 0 ? 25 : 0
}

const startDrag = (e: MouseEvent) => {
  if (!containerRef.value) return
  isDragging.value = true

  const container = containerRef.value
  const startX = e.clientX
  const startWidth = rightWidth.value
  const containerWidth = container.clientWidth

  const onMouseMove = (moveEvent: MouseEvent) => {
    if (!isDragging.value) return

    const deltaX = moveEvent.clientX - startX
    let newPercent = startWidth - (deltaX / containerWidth) * 100
    newPercent = Math.max(0, Math.min(100, newPercent))

    if (newPercent >= 80) {
      rightWidth.value = 100
      endDrag()
    } else {
      rightWidth.value = newPercent
    }
  }

  const onMouseUp = () => endDrag()

  const endDrag = () => {
    isDragging.value = false
    document.removeEventListener('mousemove', onMouseMove)
    document.removeEventListener('mouseup', onMouseUp)
  }

  document.addEventListener('mousemove', onMouseMove)
  document.addEventListener('mouseup', onMouseUp)
}

const handleMouseMove = (e: MouseEvent) => {
  const windowWidth = window.innerWidth
  const distance = windowWidth - e.clientX
  showToggleBtn.value = distance < 50
}
</script>
