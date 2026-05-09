<!-- frontend/src/components/Chat/SideCharacterPanel/CharacterSidebar.vue -->
<template>
  <div class="character-sidebar">
    <div class="panel-header">
      <h3>{{ activePanelTitle }}</h3>

      <div ref="switcherRef" class="panel-switcher">
        <button
          class="view-toggle-btn"
          :class="{ active: isMenuOpen }"
          @click="toggleMenu"
          title="切换侧栏面板"
        >
          <ArrowLeftRight :size="16" stroke-width="1.5" />
          <span class="switcher-label">切换</span>
        </button>

        <Transition name="panel-menu">
          <div v-if="isMenuOpen" class="panel-menu">
            <button
              v-for="panel in panelOrder"
              :key="panel"
              class="panel-menu-item"
              :class="{ active: activePanel === panel }"
              @click="selectPanel(panel)"
            >
              {{ panelTitles[panel] }}
            </button>
          </div>
        </Transition>
      </div>
    </div>

    <div class="panel-scrollable-content">
      <SpaceMap
        v-show="activePanel !== 'inventory'"
        :space="space"
        :player="externalPlayer"
        :combat="combat"
        :scene-units="sceneUnits"
      />

      <CharacterPanel
        v-if="activePanel === 'character'"
        :external-player="externalPlayer"
      />
      <HpOverviewPanel
        v-else-if="activePanel === 'hp'"
        :external-player="externalPlayer"
        :combat="combat"
      />
      <InventoryPanel
        v-else
        :external-player="externalPlayer"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ArrowLeftRight } from 'lucide-vue-next'
import SpaceMap from '../SpaceMap.vue'
import CharacterPanel from './CharacterPanel.vue'
import HpOverviewPanel from './HpOverviewPanel.vue'
import InventoryPanel from './InventoryPanel.vue'
import type { PlayerState } from '../../../Services_/characterStateService'

type SidebarPanelMode = 'character' | 'hp' | 'inventory'

defineProps<{
  externalPlayer: PlayerState | null
  combat?: any | null
  space?: any | null
  sceneUnits?: Record<string, any> | null
}>()

const panelOrder: SidebarPanelMode[] = ['character', 'hp', 'inventory']
const panelTitles: Record<SidebarPanelMode, string> = {
  character: '角色状态',
  hp: '生命值概览',
  inventory: '背包',
}

// 侧栏统一维护模式切换，避免 ChatPage 直接了解内部结构
const activePanel = ref<SidebarPanelMode>('character')
const isMenuOpen = ref(false)
const switcherRef = ref<HTMLElement | null>(null)

const activePanelTitle = computed(() => panelTitles[activePanel.value])

// 切换菜单改成显式选择，避免轮播式切换误触
const toggleMenu = () => {
  isMenuOpen.value = !isMenuOpen.value
}

const setViewMode = (mode: SidebarPanelMode) => {
  activePanel.value = mode
  isMenuOpen.value = false
}

const selectPanel = (mode: SidebarPanelMode) => {
  setViewMode(mode)
}

// 点击外部区域时关闭浮层，保持轻量原生感
const handleDocumentClick = (event: MouseEvent) => {
  if (!switcherRef.value) return
  if (switcherRef.value.contains(event.target as Node)) return
  isMenuOpen.value = false
}

onMounted(() => {
  document.addEventListener('click', handleDocumentClick)
})

onBeforeUnmount(() => {
  document.removeEventListener('click', handleDocumentClick)
})

defineExpose({
  setViewMode,
  selectPanel,
})
</script>

<style scoped>
.character-sidebar {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 0;
  background: rgba(30, 30, 35, 0.8);
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: #fff;
  overflow: hidden;
}

.panel-header {
  flex-shrink: 0;
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  padding: 16px 16px 8px 16px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
  position: relative;
}

.panel-header h3 {
  margin: 0;
  font-size: 18px;
  padding-top: 6px;
}

.panel-switcher {
  position: relative;
}

.view-toggle-btn {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 8px;
  padding: 8px 12px;
  background: transparent;
  border: none;
  border-radius: 12px;
  color: rgba(255, 255, 255, 0.45);
  cursor: pointer;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  font-size: 13px;
}

.view-toggle-btn:hover {
  background: rgba(255, 255, 255, 0.08);
  backdrop-filter: blur(4px);
  color: rgba(255, 255, 255, 0.75);
}

.view-toggle-btn.active {
  background: rgba(66, 184, 131, 0.12);
  color: rgba(210, 180, 140, 0.72);
  box-shadow: 0 2px 8px rgba(66, 184, 131, 0.08);
  border-left: 2px solid rgba(210, 180, 140, 0.55);
}

.switcher-label {
  font-size: 13px;
  font-weight: 470;
  white-space: nowrap;
  letter-spacing: 0.3px;
}

.panel-menu {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 136px;
  padding: 8px;
  border-radius: 16px;
  background: rgba(24, 24, 30, 0.9);
  border: 1px solid rgba(255, 255, 255, 0.08);
  backdrop-filter: blur(18px);
  box-shadow:
    0 10px 32px rgba(0, 0, 0, 0.34),
    0 0 0 1px rgba(255, 255, 255, 0.03) inset;
  z-index: 20;
}

.panel-menu-item {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  min-height: 34px;
  padding: 8px 12px;
  border: none;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.04);
  color: rgba(255, 255, 255, 0.72);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.18s ease;
}

.panel-menu-item:hover {
  background: rgba(255, 255, 255, 0.1);
  color: #f2e7d2;
}

.panel-menu-item.active {
  background: rgba(66, 184, 131, 0.12);
  color: #e6d5b8;
  box-shadow: 0 0 0 1px rgba(210, 180, 140, 0.2) inset;
}

.panel-menu-enter-active,
.panel-menu-leave-active {
  transition: opacity 0.18s ease, transform 0.18s ease;
}

.panel-menu-enter-from,
.panel-menu-leave-to {
  opacity: 0;
  transform: translateY(-6px) scale(0.98);
}

.panel-scrollable-content {
  flex: 1;
  overflow-y: auto;
  padding: 8px 16px 16px 16px;
  -ms-overflow-style: none;
  scrollbar-width: none;
}

.panel-scrollable-content::-webkit-scrollbar {
  display: none;
  width: 0;
  height: 0;
}
</style>
