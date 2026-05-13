<template>
  <section class="space-map">
    <div class="map-header">
      <div>
        <div class="section-title">战术地图</div>
        <div v-if="activeMap" class="map-subtitle">
          {{ activeMap.name }} · {{ formatNumber(activeMap.width) }}x{{ formatNumber(activeMap.height) }} 尺
        </div>
      </div>
      <div class="map-actions">
        <button
          class="map-toggle-btn"
          type="button"
          :disabled="!activeMap"
          :title="isMapCollapsed ? '显示地图' : '隐藏地图'"
          @click="toggleMapVisibility"
        >
          <component :is="isMapCollapsed ? Eye : EyeOff" :size="14" stroke-width="1.8" />
        </button>
        <button
          class="focus-player-btn"
          type="button"
          :disabled="!playerVisibleUnit"
          title="定位到主角位置"
          @click="focusPlayer"
        >
          <LocateFixed :size="14" stroke-width="1.8" />
        </button>
      </div>
    </div>

    <div v-if="!activeMap" class="empty-map">
      暂无地图数据
    </div>

    <div v-else-if="isMapCollapsed" class="empty-map">
      地图已隐藏
    </div>

    <div
      v-else
      class="map-shell"
      :class="{ interactive: isMapInteractive, panning: isPanning }"
      @click="activateMap"
      @wheel="handleMapWheel"
      @mousedown="handlePanStart"
    >
      <svg
        ref="mapCanvasRef"
        class="map-canvas"
        :viewBox="`0 0 ${viewBoxWidth} ${viewBoxHeight}`"
        role="img"
        :aria-label="`${activeMap.name} 平面地图`"
      >
        <g :transform="panTransform">
          <g :transform="viewportTransform">
            <rect
              class="map-bg"
              :x="0"
              :y="0"
              :width="viewBoxWidth"
              :height="viewBoxHeight"
              rx="0"
            />
            <path
              v-for="line in gridLines"
              :key="line.key"
              class="grid-line"
              :d="line.path"
            />
            <g
              v-for="unit in visibleUnits"
              :key="unit.id"
              class="unit-node"
              :class="[{ selected: unit.id === selectedUnitId, 'is-dead': unit.isDead }, unit.sideClass]"
              role="button"
              tabindex="0"
              :aria-label="`${unit.name} 坐标 ${formatNumber(unit.x)}, ${formatNumber(unit.y)}`"
              @click.stop="handleUnitClick(unit.id)"
              @keydown.enter.prevent="selectedUnitId = unit.id"
              @keydown.space.prevent="selectedUnitId = unit.id"
            >
              <circle class="unit-aura" :cx="unit.screenX" :cy="unit.screenY" :r="unit.selected ? 2.25 : 1.75" />
              <circle class="unit-dot" :cx="unit.screenX" :cy="unit.screenY" :r="1" />
              <text
                class="unit-label"
                :class="{ expanded: showFullLabels }"
                :x="unit.screenX + (showFullLabels ? 2.2 : 0)"
                :y="unit.screenY - (showFullLabels ? 2 : 3.25)"
                :text-anchor="showFullLabels ? 'start' : 'middle'"
              >
                {{ showFullLabels ? unit.name : unit.initial }}
              </text>
            </g>
          </g>
        </g>
      </svg>
      <div class="axis-row">
        <span class="zoom-indicator">
          {{
            isPanning
              ? '拖动中'
              : isMapInteractive
                ? `缩放 ${zoomScale.toFixed(1)}x；按住 Ctrl + 鼠标拖动`
                : '点击地图后可滚轮缩放；按住 Ctrl + 鼠标拖动'
          }}
        </span>
      </div>
    </div>

    <div v-if="selectedUnit && !isMapCollapsed" class="unit-detail">
      <div class="unit-detail-head">
        <span class="unit-name">{{ selectedUnit.name }}</span>
        <span class="unit-id">{{ selectedUnit.id }}</span>
      </div>
      <div class="detail-grid">
        <div>
          <span>坐标</span>
          <strong>({{ formatNumber(selectedUnit.x) }}, {{ formatNumber(selectedUnit.y) }})</strong>
        </div>
        <div>
          <span>阵营</span>
          <strong>{{ sideLabel(selectedUnit.side) }}</strong>
        </div>
        <div v-if="selectedUnit.hp !== undefined">
          <span>生命值</span>
          <strong>{{ selectedUnit.hp }} / {{ selectedUnit.max_hp ?? '?' }}</strong>
        </div>
        <div v-if="selectedUnit.ac !== undefined">
          <span>护甲</span>
          <strong>{{ selectedUnit.ac }}</strong>
        </div>
      </div>
      <div v-if="selectedUnit.conditions.length" class="condition-line">
        <span v-for="condition in selectedUnit.conditions" :key="condition" class="mini-condition">
          {{ condition }}
        </span>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Eye, EyeOff, LocateFixed } from 'lucide-vue-next'

type PlaneMap = {
  id: string
  name: string
  width: number
  height: number
  grid_size?: number
}

type UnitInfo = {
  id: string
  name?: string
  side?: string
  hp?: number
  max_hp?: number
  ac?: number
  conditions?: Array<{ id?: string; name_cn?: string }>
}

type VisibleUnit = {
  id: string
  name: string
  side: string
  sideClass: string
  initial: string
  x: number
  y: number
  screenX: number
  screenY: number
  selected: boolean
  isDead: boolean
  hp?: number
  max_hp?: number
  ac?: number
  conditions: string[]
}

type LooseRecord = Record<string, any>

const props = defineProps<{
  space: any | null
  player: any | null
  combat?: any | null
  sceneUnits?: Record<string, any> | null
  deadUnits?: Record<string, any> | null
}>()

const selectedUnitId = ref<string | null>(null)
const isMapCollapsed = ref(false)
const isMapInteractive = ref(false)
const zoomScale = ref(1)
const panX = ref(0)
const panY = ref(0)
const isPanning = ref(false)
const mapCanvasRef = ref<SVGSVGElement | null>(null)
const panStartState = ref<{ mouseX: number; mouseY: number; panX: number; panY: number } | null>(null)
const isCtrlPressed = ref(false)
const lastCtrlKeydownAt = ref(0)

// 地图状态来自多路流式更新，先做宽松归一化，避免中间态直接打断整页渲染
const isRecord = (value: unknown): value is LooseRecord => {
  return typeof value === 'object' && value !== null
}

const toEntries = (value: unknown): Array<[string, any]> => {
  return isRecord(value) ? Object.entries(value) : []
}

const toNumber = (value: unknown, fallback: number): number => {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : fallback
}

const toOptionalNumber = (value: unknown): number | undefined => {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : undefined
}

const toLabelText = (value: unknown, fallback: string): string => {
  if (typeof value === 'string' && value.trim()) return value
  if (typeof value === 'number') return String(value)
  return fallback
}

const normalizeConditions = (value: unknown): string[] => {
  if (!Array.isArray(value)) return []

  return value.map((condition) => {
    if (typeof condition === 'string' || typeof condition === 'number') {
      return String(condition)
    }
    if (isRecord(condition)) {
      return toLabelText(condition.name_cn ?? condition.id, '?')
    }
    return '?'
  })
}

const activeMap = computed<PlaneMap | null>(() => {
  if (!isRecord(props.space)) return null

  const maps = isRecord(props.space.maps) ? props.space.maps : null
  const activeMapId = toLabelText(props.space.active_map_id, '')
  if (!maps || !activeMapId) return null

  const rawMap = maps[activeMapId]
  if (!isRecord(rawMap)) return null

  return {
    id: toLabelText(rawMap.id, activeMapId),
    name: toLabelText(rawMap.name, activeMapId),
    width: toNumber(rawMap.width, 1),
    height: toNumber(rawMap.height, 1),
    grid_size: toOptionalNumber(rawMap.grid_size),
  }
})

const viewBoxWidth = computed(() => Math.max(1, Number(activeMap.value?.width ?? 1)))
const viewBoxHeight = computed(() => Math.max(1, Number(activeMap.value?.height ?? 1)))
const panTransform = computed(() => `translate(${panX.value} ${panY.value})`)
const viewportTransform = computed(() => {
  const centerX = viewBoxWidth.value / 2
  const centerY = viewBoxHeight.value / 2
  return [
    `translate(${centerX} ${centerY})`,
    `scale(${zoomScale.value})`,
    `translate(${-centerX} ${-centerY})`,
  ].join(' ')
})
const showFullLabels = computed(() => zoomScale.value >= 1.8)

const unitsById = computed<Record<string, UnitInfo>>(() => {
  const result: Record<string, UnitInfo> = {}

  toEntries(props.sceneUnits).forEach(([id, unit]) => {
    result[id] = isRecord(unit) ? { ...(unit as UnitInfo), id } : { id }
  })

  const participants = isRecord(props.combat) ? props.combat.participants : null
  toEntries(participants).forEach(([id, unit]) => {
    result[id] = isRecord(unit) ? { ...(unit as UnitInfo), id } : { id }
  })

  if (isRecord(props.player)) {
    const playerName = toLabelText(props.player.name, 'player')
    const playerId = toLabelText(props.player.id, `player_${playerName}`)
    result[playerId] = { id: playerId, ...props.player, side: 'player' }
  }

  toEntries(props.deadUnits).forEach(([id, unit]) => {
    const current = result[id] ?? { id }
    result[id] = isRecord(unit) ? { ...current, ...(unit as UnitInfo), id } : current
  })

  return result
})

const deadUnitIds = computed(() => {
  const ids = new Set<string>()

  toEntries(props.deadUnits).forEach(([id]) => {
    ids.add(id)
  })

  toEntries(props.sceneUnits).forEach(([id, unit]) => {
    if (isRecord(unit) && toNumber(unit.hp, 1) <= 0) ids.add(id)
  })

  const participants = isRecord(props.combat) ? props.combat.participants : null
  toEntries(participants).forEach(([id, unit]) => {
    if (isRecord(unit) && toNumber(unit.hp, 1) <= 0) ids.add(id)
  })

  if (isRecord(props.player)) {
    const playerName = toLabelText(props.player.name, 'player')
    const playerId = toLabelText(props.player.id, `player_${playerName}`)
    if (toNumber(props.player.hp, 1) <= 0) ids.add(playerId)
  }

  return ids
})

const visibleUnits = computed<VisibleUnit[]>(() => {
  const map = activeMap.value
  const placements = isRecord(props.space) && isRecord(props.space.placements) ? props.space.placements : {}
  const combatActive = isRecord(props.combat)
  if (!map) return []

  return toEntries(placements)
    .map(([unitId, rawPlacement]) => {
      const placement = isRecord(rawPlacement) ? rawPlacement : {}
      const position = isRecord(placement.position) ? placement.position : {}
      const x = toNumber(position.x, 0)
      const y = toNumber(position.y, 0)
      const info = unitsById.value[unitId] ?? { id: unitId }
      const side = typeof info.side === 'string' && info.side ? info.side : 'neutral'
      const name = toLabelText(info.name, unitId)
      const selected = unitId === selectedUnitId.value
      const isDead = deadUnitIds.value.has(unitId)

      return {
        id: unitId,
        name,
        side,
        sideClass: sideClass(side),
        initial: name.slice(0, 1).toUpperCase(),
        x,
        y,
        screenX: clamp(x, 0, map.width),
        screenY: clamp(map.height - y, 0, map.height),
        selected,
        isDead,
        hp: toOptionalNumber(info.hp),
        max_hp: toOptionalNumber(info.max_hp),
        ac: toOptionalNumber(info.ac),
        conditions: normalizeConditions(info.conditions),
      }
    })
    .filter((unit) => {
      const placement = placements[unit.id]
      if (!isRecord(placement) || toLabelText(placement.map_id, '') !== map.id) return false
      if (!combatActive && unit.side === 'enemy') return false
      return true
    })
})

const selectedUnit = computed(() => {
  return visibleUnits.value.find((unit) => unit.id === selectedUnitId.value) ?? visibleUnits.value[0] ?? null
})

const playerUnitId = computed(() => {
  if (!isRecord(props.player)) return null
  const playerName = toLabelText(props.player.name, 'player')
  return toLabelText(props.player.id, `player_${playerName}`)
})

const playerVisibleUnit = computed(() => {
  const unitId = playerUnitId.value
  if (!unitId) return null
  return visibleUnits.value.find((unit) => unit.id === unitId) ?? null
})

const gridLines = computed(() => {
  const map = activeMap.value
  if (!map) return []

  const step = Math.max(5, Number(map.grid_size || 5))
  const lines: Array<{ key: string; path: string }> = []

  for (let x = step; x < map.width; x += step) {
    lines.push({ key: `x-${x}`, path: `M ${x} 0 L ${x} ${map.height}` })
  }
  for (let y = step; y < map.height; y += step) {
    lines.push({ key: `y-${y}`, path: `M 0 ${y} L ${map.width} ${y}` })
  }

  return lines
})

watch(visibleUnits, (units) => {
  if (selectedUnitId.value && units.some((unit) => unit.id === selectedUnitId.value)) return
  selectedUnitId.value = units[0]?.id ?? null
}, { immediate: true })

watch(activeMap, () => {
  resetViewport()
  isMapInteractive.value = false
  isMapCollapsed.value = false
})

watch(zoomScale, () => {
  clampPanIntoBounds()
})

const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value))

const maxPanX = computed(() => Math.max(0, (viewBoxWidth.value * (zoomScale.value - 1)) / 2))
const maxPanY = computed(() => Math.max(0, (viewBoxHeight.value * (zoomScale.value - 1)) / 2))

const clampPanIntoBounds = () => {
  panX.value = clamp(Number(panX.value.toFixed(2)), -maxPanX.value, maxPanX.value)
  panY.value = clamp(Number(panY.value.toFixed(2)), -maxPanY.value, maxPanY.value)
}

const resetViewport = () => {
  zoomScale.value = 1
  panX.value = 0
  panY.value = 0
  isPanning.value = false
  panStartState.value = null
}

const activateMap = (event?: MouseEvent) => {
  const now = Date.now()
  if (event?.ctrlKey || isCtrlPressed.value || now - lastCtrlKeydownAt.value <= 560 || isPanning.value) {
    return
  }
  if (isMapInteractive.value) {
    resetViewport()
    isMapInteractive.value = false
    return
  }
  isMapInteractive.value = true
}

const toggleMapVisibility = () => {
  isMapCollapsed.value = !isMapCollapsed.value
  if (isMapCollapsed.value) {
    isMapInteractive.value = false
    isPanning.value = false
  }
}

const handleMapWheel = (event: WheelEvent) => {
  if (!isMapInteractive.value) return
  event.preventDefault()
  const nextScale = zoomScale.value + (event.deltaY < 0 ? 0.2 : -0.2)
  zoomScale.value = clamp(Number(nextScale.toFixed(2)), 1, 3)
  clampPanIntoBounds()
}

const handlePanStart = (event: MouseEvent) => {
  if (!isMapInteractive.value || !event.ctrlKey || !mapCanvasRef.value) return
  if (zoomScale.value <= 1) return
  event.preventDefault()
  event.stopPropagation()
  isPanning.value = true
  panStartState.value = {
    mouseX: event.clientX,
    mouseY: event.clientY,
    panX: panX.value,
    panY: panY.value,
  }
  window.addEventListener('mousemove', handlePanMove)
  window.addEventListener('mouseup', handlePanEnd)
}

const handlePanMove = (event: MouseEvent) => {
  if (!isPanning.value || !panStartState.value || !mapCanvasRef.value) return
  const rect = mapCanvasRef.value.getBoundingClientRect()
  if (!rect.width || !rect.height) return

  const deltaX = (event.clientX - panStartState.value.mouseX) * (viewBoxWidth.value / rect.width) / zoomScale.value
  const deltaY = (event.clientY - panStartState.value.mouseY) * (viewBoxHeight.value / rect.height) / zoomScale.value

  panX.value = Number((panStartState.value.panX + deltaX).toFixed(2))
  panY.value = Number((panStartState.value.panY + deltaY).toFixed(2))
  clampPanIntoBounds()
}

const handlePanEnd = () => {
  isPanning.value = false
  panStartState.value = null
  window.removeEventListener('mousemove', handlePanMove)
  window.removeEventListener('mouseup', handlePanEnd)
}

const handleKeyDown = (event: KeyboardEvent) => {
  if (event.key !== 'Control') return
  isCtrlPressed.value = true
  lastCtrlKeydownAt.value = Date.now()
}

const handleKeyUp = (event: KeyboardEvent) => {
  if (event.key !== 'Control') return
  isCtrlPressed.value = false
}

onMounted(() => {
  window.addEventListener('keydown', handleKeyDown)
  window.addEventListener('keyup', handleKeyUp)
})

onBeforeUnmount(() => {
  handlePanEnd()
  window.removeEventListener('keydown', handleKeyDown)
  window.removeEventListener('keyup', handleKeyUp)
})

const handleUnitClick = (unitId: string) => {
  selectedUnitId.value = unitId
}

const focusPlayer = () => {
  const unit = playerVisibleUnit.value
  if (!unit) return

  selectedUnitId.value = unit.id
  isMapInteractive.value = true

  if (zoomScale.value <= 1) {
    panX.value = 0
    panY.value = 0
    return
  }

  const centerX = viewBoxWidth.value / 2
  const centerY = viewBoxHeight.value / 2
  panX.value = (centerX - unit.screenX) * (zoomScale.value - 1)
  panY.value = (centerY - unit.screenY) * (zoomScale.value - 1)
  clampPanIntoBounds()
}

const formatNumber = (value: number | undefined) => {
  if (value === undefined || Number.isNaN(value)) return '?'
  return Number.isInteger(value) ? String(value) : value.toFixed(1)
}

const sideLabel = (side: string) => {
  if (side === 'player') return '玩家'
  if (side === 'ally') return '友方'
  if (side === 'enemy') return '敌方'
  return '中立'
}

const sideClass = (side: string) => {
  if (side === 'player') return 'side-player'
  if (side === 'ally') return 'side-ally'
  if (side === 'enemy') return 'side-enemy'
  return 'side-neutral'
}
</script>

<style scoped>
.space-map {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 8px 0 12px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}

.map-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}

.map-actions {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.section-title {
  color: #c9a87b;
  font-size: 14px;
  font-weight: 600;
}

.map-subtitle {
  margin-top: 3px;
  color: #a1a1aa;
  font-size: 12px;
}

.focus-player-btn {
  width: 28px;
  height: 28px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 0.5px solid rgba(255, 255, 255, 0.16);
  background: rgba(255, 255, 255, 0.04);
  color: #cbd5e1;
  border-radius: 6px;
  cursor: pointer;
}

.map-toggle-btn {
  width: 28px;
  height: 28px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 0.5px solid rgba(255, 255, 255, 0.16);
  background: rgba(255, 255, 255, 0.04);
  color: #cbd5e1;
  border-radius: 6px;
  cursor: pointer;
}

.map-toggle-btn:disabled,
.focus-player-btn:disabled {
  opacity: 0.35;
  cursor: default;
}

.map-shell {
  width: 100%;
}

.map-shell.interactive {
  cursor: zoom-in;
}

.map-shell.interactive .map-canvas {
  border-color: rgba(250, 204, 21, 0.45);
  box-shadow: 0 0 0 1px rgba(250, 204, 21, 0.12) inset;
}

.map-shell.panning,
.map-shell.panning .map-canvas {
  cursor: grabbing;
}

.map-canvas {
  width: 100%;
  aspect-ratio: 1 / 1;
  max-height: 260px;
  display: block;
  border: 1px solid rgba(255, 255, 255, 0.14);
  background: #17181d;
}

.map-bg {
  fill: #191b21;
}

.grid-line {
  fill: none;
  stroke: rgba(255, 255, 255, 0.08);
  stroke-width: 0.55;
  vector-effect: non-scaling-stroke;
}

.unit-node {
  cursor: pointer;
  outline: none;
}

.unit-aura {
  fill: rgba(255, 255, 255, 0.08);
  stroke: rgba(255, 255, 255, 0.25);
  stroke-width: 1;
  vector-effect: non-scaling-stroke;
}

.unit-dot {
  stroke: rgba(0, 0, 0, 0.65);
  stroke-width: 0.7;
  vector-effect: non-scaling-stroke;
}

.unit-label {
  fill: #f8fafc;
  font-size: 4px;
  font-weight: 700;
  text-anchor: middle;
  paint-order: stroke;
  stroke: rgba(0, 0, 0, 0.75);
  stroke-width: 1.3;
  pointer-events: none;
}

.unit-label.expanded {
  font-size: 3.1px;
}

.unit-node.selected .unit-aura {
  fill: rgba(250, 204, 21, 0.18);
  stroke: #facc15;
}

.side-player .unit-dot {
  fill: #38bdf8;
}

.side-ally .unit-dot {
  fill: #22c55e;
}

.side-enemy .unit-dot {
  fill: #ef4444;
}

.side-neutral .unit-dot {
  fill: #a78bfa;
}

.unit-node .unit-aura {
  opacity: 0.9;
}

.unit-node.is-dead .unit-dot,
.unit-node.is-dead.side-player .unit-dot,
.unit-node.is-dead.side-ally .unit-dot,
.unit-node.is-dead.side-enemy .unit-dot,
.unit-node.is-dead.side-neutral .unit-dot {
  fill: #6b7280;
}

.unit-node.is-dead .unit-aura {
  fill: rgba(107, 114, 128, 0.12);
  stroke: rgba(148, 163, 184, 0.42);
}

.unit-node.is-dead .unit-label {
  fill: #d4d4d8;
}

.axis-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  color: #71717a;
  font-size: 11px;
  margin-top: 4px;
}

.zoom-indicator {
  flex: 1;
  text-align: center;
  color: #a1a1aa;
}

.unit-detail {
  background: rgba(0, 0, 0, 0.28);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 8px;
  padding: 10px;
}

.unit-detail-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
}

.unit-name {
  color: #f4f4f5;
  font-size: 14px;
  font-weight: 700;
}

.unit-id {
  color: #71717a;
  font-size: 11px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.detail-grid div {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.detail-grid span {
  color: #8e8e93;
  font-size: 11px;
}

.detail-grid strong {
  color: #e5e7eb;
  font-size: 13px;
  font-weight: 600;
}

.condition-line {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  margin-top: 8px;
}

.mini-condition {
  padding: 2px 6px;
  color: #fca5a5;
  background: rgba(239, 68, 68, 0.16);
  border-radius: 6px;
  font-size: 11px;
}

.empty-map {
  color: #8e8e93;
  font-size: 13px;
  text-align: center;
  padding: 18px 0;
}
</style>
