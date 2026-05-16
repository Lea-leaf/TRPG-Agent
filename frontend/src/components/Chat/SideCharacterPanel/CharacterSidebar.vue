<!-- frontend/src/components/Chat/SideCharacterPanel/CharacterSidebar.vue -->
<template>
  <div class="character-sidebar">
    <div class="panel-header">
      <div class="header-title-row">
        <h3>{{ activePanelTitle }}</h3>
        <button
          v-if="showLeftRailToggleButton"
          class="left-rail-toggle-btn"
          type="button"
          :title="leftRailToggleTitle"
          @click="toggleLeftRailMode"
        >
          {{ leftRailToggleLabel }}
        </button>
      </div>

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
        :dead-units="deadUnits"
        :send-tactical-move-request="sendTacticalMoveRequest"
        @selected-unit-change="handleSelectedUnitChange"
      />

      <CharacterPanel
        v-if="activePanel === 'character'"
        :external-player="externalPlayer"
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
import InventoryPanel from './InventoryPanel.vue'
import { LEFT_RAIL_MODE_EVENT, overrideLeftRailMode } from '../../../Services_/leftRailService'
import type { PlayerState } from '../../../Services_/characterStateService'
import type { AvailabilitySelectionUnit } from '../../../Services_/actionAvailabilityService'

type SidebarPanelMode = 'character' | 'inventory'

const props = defineProps<{
  externalPlayer: PlayerState | null
  combat?: any | null
  space?: any | null
  sceneUnits?: Record<string, any> | null
  deadUnits?: Record<string, any> | null
  sendTacticalMoveRequest?: ((message: string) => Promise<void>) | null
}>()

const emit = defineEmits<{
  selectedUnitChange: [unit: AvailabilitySelectionUnit | null]
}>()

const panelOrder: SidebarPanelMode[] = ['character', 'inventory']
const panelTitles: Record<SidebarPanelMode, string> = {
  character: '角色状态',
  inventory: '背包',
}

// 侧栏统一维护模式切换，避免 ChatPage 直接了解内部结构
const activePanel = ref<SidebarPanelMode>('character')
const isMenuOpen = ref(false)
const switcherRef = ref<HTMLElement | null>(null)
const selectedUnit = ref<AvailabilitySelectionUnit | null>(null)
const leftRailMode = ref<'navigation' | 'combat'>('navigation')

const activePanelTitle = computed(() => panelTitles[activePanel.value])
const showLeftRailToggleButton = computed(() => isCombatActive(props.combat))
const leftRailToggleLabel = computed(() => leftRailMode.value === 'combat' ? '返回导航' : '显示时间轴')
const leftRailToggleTitle = computed(() => leftRailMode.value === 'combat' ? '切回默认导航栏' : '切回战斗时间轴')

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

// 侧栏继续做轻量转发层，避免聊天页直接依赖地图组件。
const handleSelectedUnitChange = (unit: AvailabilitySelectionUnit | null) => {
  selectedUnit.value = unit
  emit('selectedUnitChange', unit)
}

const toggleLeftRailMode = () => {
  overrideLeftRailMode(leftRailMode.value === 'combat' ? 'navigation' : 'combat')
}

const handleLeftRailMode = (event: Event) => {
  const mode = (event as CustomEvent<'navigation' | 'combat'>).detail
  leftRailMode.value = mode
}

// 点击外部区域时关闭浮层，保持轻量原生感
const handleDocumentClick = (event: MouseEvent) => {
  if (!switcherRef.value) return
  if (switcherRef.value.contains(event.target as Node)) return
  isMenuOpen.value = false
}

onMounted(() => {
  document.addEventListener('click', handleDocumentClick)
  window.addEventListener(LEFT_RAIL_MODE_EVENT, handleLeftRailMode as EventListener)
})

onBeforeUnmount(() => {
  document.removeEventListener('click', handleDocumentClick)
  window.removeEventListener(LEFT_RAIL_MODE_EVENT, handleLeftRailMode as EventListener)
})

defineExpose({
  setViewMode,
  selectPanel,
})

function isCombatActive(combat: unknown): boolean {
  if (!combat || typeof combat !== 'object') return false
  const participants = (combat as Record<string, any>).participants
  return !!(participants && typeof participants === 'object' && Object.keys(participants).length > 0)
}
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

.header-title-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.panel-header h3 {
  margin: 0;
  font-size: 18px;
  padding-top: 6px;
}

.left-rail-toggle-btn {
  height: 28px;
  padding: 0 10px;
  border: 1px solid rgba(201, 168, 123, 0.22);
  border-radius: 999px;
  background: rgba(201, 168, 123, 0.08);
  color: #dcc092;
  font-size: 11px;
  cursor: pointer;
  transition: all 0.18s ease;
  white-space: nowrap;
}

.left-rail-toggle-btn:hover {
  background: rgba(201, 168, 123, 0.14);
  border-color: rgba(201, 168, 123, 0.34);
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
