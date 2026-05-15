<template>
  <aside :class="['combat-timeline-panel', { collapsed: isCollapsed }]">
    <HpOverviewPanel
      :external-player="player"
      :combat="combat"
      :space="space"
      :selected-unit="selectedUnit"
      :send-combat-action-request="sendCombatActionRequest"
      @action-notice="handleActionNotice"
    />
  </aside>
</template>

<script setup lang="ts">
import HpOverviewPanel from './HpOverviewPanel.vue'
import type { AvailabilitySelectionUnit } from '../../../Services_/actionAvailabilityService'
import type { PlayerState } from '../../../Services_/characterStateService'

const props = defineProps<{
  player: PlayerState | null
  combat: Record<string, any> | null
  space: Record<string, any> | null
  selectedUnit: AvailabilitySelectionUnit | null
  sendCombatActionRequest?: ((message: string) => Promise<void>) | null
  isCollapsed?: boolean
}>()

const emit = defineEmits<{
  actionNotice: [text: string]
}>()

const handleActionNotice = (text: string) => {
  emit('actionNotice', text)
}
</script>

<style scoped>
.combat-timeline-panel {
  width: 240px;
  display: flex;
  flex-direction: column;
  height: 100vh;
  flex-shrink: 0;
  position: sticky;
  top: 0;
  left: 0;
  padding: 16px 14px;
  background: rgba(18, 18, 24, 0.86);
  backdrop-filter: blur(16px);
  border-right: 1px solid rgba(255, 255, 255, 0.08);
  color: #f3eee4;
  overflow-y: auto;
  -ms-overflow-style: none;
  scrollbar-width: none;
  transition: width 0.3s cubic-bezier(0.4, 0, 0.2, 1), padding 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.combat-timeline-panel::-webkit-scrollbar {
  display: none;
  width: 0;
  height: 0;
}

.combat-timeline-panel.collapsed {
  width: 72px;
  padding-left: 8px;
  padding-right: 8px;
}

</style>
