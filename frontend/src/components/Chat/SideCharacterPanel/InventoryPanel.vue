<!-- frontend/src/components/Chat/SideCharacterPanel/InventoryPanel.vue -->
<template>
  <div class="inventory-panel">
    <div v-if="inventoryEntries.length" class="inventory-section">
      <div class="section-title">随身物品</div>
      <div class="inventory-list">
        <div
          v-for="entry in inventoryEntries"
          :key="entry.key"
          class="inventory-item"
        >
          <div class="item-main">
            <div class="item-name-row">
              <span class="item-name">{{ entry.name }}</span>
              <span class="item-kind">{{ entry.kind }}</span>
            </div>
            <div v-if="entry.detail" class="item-detail">{{ entry.detail }}</div>
          </div>
          <span class="item-quantity">{{ entry.quantityText }}</span>
        </div>
      </div>
    </div>

    <div v-else class="empty-state">
      暂无可展示的背包物品
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { PlayerState, WeaponData } from '../../../Services_/characterStateService'
import { translateWeaponName } from '../../../Services_/nameTranslator'

type InventoryEntry = {
  key: string
  name: string
  kind: string
  detail: string
  quantityText: string
}

const props = defineProps<{
  externalPlayer: PlayerState | null
}>()

// 背包页直接消费后端当前真实会传的 weapons；后续若接入 items 字段，在这里扩展即可
const inventoryEntries = computed<InventoryEntry[]>(() => {
  const player = props.externalPlayer
  if (!player) return []

  return (player.weapons ?? [])
    .filter((weapon): weapon is WeaponData => Boolean(weapon?.name))
    .map((weapon, index) => ({
      key: `${weapon.name}-${index}`,
      name: translateWeaponName(weapon.name),
      kind: '武器',
      detail: [weapon.damage_dice, weapon.damage_type].filter(Boolean).join(' '),
      quantityText: 'x1',
    }))
})
</script>

<style scoped>
.inventory-panel {
  min-height: 220px;
}

.inventory-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.section-title {
  font-size: 14px;
  font-weight: 600;
  color: #c9a87b;
  letter-spacing: 1px;
}

.inventory-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.inventory-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  border-radius: 12px;
  background: rgba(0, 0, 0, 0.24);
  border: 1px solid rgba(255, 255, 255, 0.06);
}

.item-main {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.item-name-row {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.item-name {
  color: #e8e5dc;
  font-size: 14px;
  font-weight: 600;
}

.item-kind {
  flex-shrink: 0;
  padding: 2px 8px;
  border-radius: 999px;
  background: rgba(201, 168, 123, 0.14);
  color: #d4b58a;
  font-size: 11px;
}

.item-detail {
  color: #9ca3af;
  font-size: 12px;
}

.item-quantity {
  flex-shrink: 0;
  color: #d6d3d1;
  font-size: 13px;
  font-family: monospace;
}

.empty-state {
  color: #8e8e93;
  font-style: italic;
  text-align: center;
  padding: 20px 0;
}
</style>
