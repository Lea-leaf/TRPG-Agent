<!-- frontend/src/components/Chat/SideCharacterPanel/HpOverviewPanel.vue -->
<template>
  <div class="hp-overview">
    <div v-if="hpUnits.length === 0" class="empty-state">
      暂无单位血量数据
    </div>
    <div v-for="unit in hpUnits" :key="unit.id" class="hp-overview-item">
      <HpBar
        :name="unit.name"
        :old-hp="unit.hp"
        :new-hp="unit.hp"
        :max-hp="unit.max_hp"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import HpBar from './HpBar.vue'
import type { PlayerState } from '../../../Services_/characterStateService'

const props = defineProps<{
  externalPlayer: PlayerState | null
  combat?: any | null
}>()

const hpUnits = computed(() => {
  const units: Array<{ id: string; name: string; hp: number; max_hp: number }> = []

  if (props.externalPlayer) {
    units.push({
      id: `player_${props.externalPlayer.name}`,
      name: props.externalPlayer.name || '玩家',
      hp: props.externalPlayer.hp || 0,
      max_hp: props.externalPlayer.max_hp || 1,
    })
  }

  if (props.combat?.participants) {
    Object.values(props.combat.participants).forEach((participant: any) => {
      if (participant.id?.startsWith('player_') && units.some(unit => unit.id === participant.id)) return
      units.push({
        id: participant.id,
        name: participant.name,
        hp: participant.hp,
        max_hp: participant.max_hp,
      })
    })
  }

  return units
})
</script>

<style scoped>
.hp-overview {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.empty-state {
  color: #8e8e93;
  font-style: italic;
  text-align: center;
  padding: 20px 0;
}
</style>
