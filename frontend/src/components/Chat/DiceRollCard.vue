<template>
  <div class="dice-roll-wrapper">
    <section class="dice-roll-card" :class="outcomeClass">
      <div class="corner top-left"></div>
      <div class="corner top-right"></div>
      <div class="corner bottom-left"></div>
      <div class="corner bottom-right"></div>

      <header class="dice-roll-header">
        <div>
          <p class="roll-kicker">{{ rollKindLabel }}</p>
          <h2>{{ title }}</h2>
          <p class="roll-formula">{{ formulaText }}</p>
        </div>
        <div v-if="hasTarget" class="roll-target">
          <span>{{ targetLabel }}</span>
          <strong>{{ roll.target }}</strong>
        </div>
      </header>

      <div class="dice-stage">
        <D20RollEmblem :value="roll.raw_roll" />
      </div>

      <p class="roll-total">{{ totalFormula }}</p>
      <p v-if="hasTarget" class="roll-outcome">{{ outcomeText }}</p>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import D20RollEmblem from './D20RollEmblem.vue'
import type { DiceRollEvent } from '../../Services_/chatService'

const props = defineProps<{
  roll: DiceRollEvent
}>()

const title = computed(() => props.roll.title || (props.roll.kind === 'attack' ? 'Attack Roll' : 'D20 Check'))
const modifier = computed(() => props.roll.modifier ?? props.roll.final_total - props.roll.raw_roll)
const hasTarget = computed(() => typeof props.roll.target === 'number')
const targetLabel = computed(() => props.roll.target_label || (props.roll.kind === 'attack' ? 'AC' : 'DC'))
const rollKindLabel = computed(() => props.roll.kind === 'attack' ? 'ATTACK ROLL' : 'ABILITY CHECK')
const formulaText = computed(() => {
  const parts = [props.roll.formula || '1d20']
  if (props.roll.advantage === 'advantage') parts.push('优势')
  if (props.roll.advantage === 'disadvantage') parts.push('劣势')
  return parts.join(' · ')
})
const totalFormula = computed(() => {
  const sign = modifier.value >= 0 ? '+' : '-'
  return `${props.roll.raw_roll} ${sign} ${Math.abs(modifier.value)} = ${props.roll.final_total}`
})
const isSuccess = computed(() => hasTarget.value && props.roll.final_total >= Number(props.roll.target))
const outcomeClass = computed(() => {
  if (!hasTarget.value) return 'neutral'
  return isSuccess.value ? 'success' : 'failure'
})
const outcomeText = computed(() => isSuccess.value ? 'SUCCESS' : 'FAILURE')

</script>

<style scoped>
.dice-roll-wrapper {
  padding: 16px 0;
  animation: fadeInUp 0.3s ease-out;
}

.dice-roll-card {
  position: relative;
  overflow: hidden;
  min-height: 390px;
  border: 1px solid rgba(196, 146, 58, 0.85);
  border-radius: 8px;
  background:
    radial-gradient(circle at 50% 42%, rgba(44, 70, 200, 0.22), transparent 34%),
    linear-gradient(135deg, rgba(24, 20, 60, 0.98), rgba(6, 15, 38, 0.98));
  box-shadow: 0 14px 34px rgba(0, 0, 0, 0.42), inset 0 0 0 1px rgba(245, 210, 120, 0.16);
  color: #f8edc0;
  font-family: 'Cinzel', 'Georgia', serif;
}

.dice-roll-card::before {
  content: '';
  position: absolute;
  inset: 14px;
  border: 1px solid rgba(196, 146, 58, 0.38);
  border-radius: 5px;
  pointer-events: none;
}

.dice-roll-header {
  position: relative;
  z-index: 2;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
  padding: 24px 28px 0;
}

.roll-kicker,
.roll-formula {
  margin: 0;
  color: #cdb37b;
  font-size: 13px;
  font-weight: 700;
  letter-spacing: 0;
}

.dice-roll-header h2 {
  margin: 4px 0 8px;
  color: #fff5c9;
  font-size: 26px;
  line-height: 1.1;
}

.roll-target {
  min-width: 132px;
  padding: 14px 18px;
  border: 1px solid rgba(196, 146, 58, 0.75);
  border-radius: 8px;
  background: rgba(17, 29, 53, 0.82);
  text-align: center;
}

.roll-target span {
  display: block;
  color: #fff0ba;
  font-size: 12px;
  font-weight: 800;
  letter-spacing: 0;
}

.roll-target strong {
  display: block;
  margin-top: 4px;
  color: #fff8d8;
  font-size: 34px;
  line-height: 1;
}

.dice-stage {
  position: relative;
  z-index: 1;
  width: min(390px, 72vw);
  height: 225px;
  margin: 2px auto 0;
  display: flex;
  align-items: center;
  justify-content: center;
}

.roll-total {
  position: relative;
  z-index: 2;
  margin: 0;
  color: #f4df9a;
  font-size: 15px;
  font-weight: 800;
  text-align: center;
}

.roll-outcome {
  position: relative;
  z-index: 2;
  margin: 18px 0 26px;
  font-size: 38px;
  font-weight: 900;
  line-height: 1;
  text-align: center;
  letter-spacing: 0;
}

.success .roll-outcome {
  color: #45f08a;
}

.failure .roll-outcome {
  color: #ff6b6b;
}

.corner {
  position: absolute;
  width: 78px;
  height: 78px;
  border-color: rgba(196, 146, 58, 0.82);
  pointer-events: none;
}

.top-left {
  top: 10px;
  left: 10px;
  border-top: 2px solid;
  border-left: 2px solid;
}

.top-right {
  top: 10px;
  right: 10px;
  border-top: 2px solid;
  border-right: 2px solid;
}

.bottom-left {
  bottom: 10px;
  left: 10px;
  border-bottom: 2px solid;
  border-left: 2px solid;
}

.bottom-right {
  right: 10px;
  bottom: 10px;
  border-right: 2px solid;
  border-bottom: 2px solid;
}

@keyframes fadeInUp {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@media (max-width: 720px) {
  .dice-roll-card {
    min-height: 360px;
  }

  .dice-roll-header {
    padding: 24px 22px 0;
  }

  .dice-roll-header h2 {
    font-size: 22px;
  }

  .roll-target {
    min-width: 92px;
    padding: 12px;
  }

  .dice-stage {
    width: min(320px, 82vw);
    height: 210px;
  }

  .roll-outcome {
    font-size: 32px;
  }
}
</style>
