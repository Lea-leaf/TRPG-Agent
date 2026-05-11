<template>
  <div class="settings-page">
    <div class="settings-shell">
      <header class="settings-hero">
        <div class="hero-copy-block">
          <p class="eyebrow">Settings</p>
          <h1>设置</h1>
        </div>
        <div class="hero-actions">
          <button class="secondary-btn" type="button" @click="resetSettings">
            恢复默认
          </button>
        </div>
      </header>

      <section class="settings-flow">
        <article class="settings-section">
          <div class="card-header">
            <div>
              <p class="card-kicker">Chat</p>
              <h2>聊天</h2>
            </div>
          </div>

          <div class="setting-item slider-row">
            <div class="setting-copy">
              <h3>字体尺寸</h3>
              <p>拖动滑块调节聊天文本显示比例。</p>
            </div>
            <div class="slider-control">
              <input
                :value="settings.fontScale"
                class="range-slider"
                type="range"
                min="85"
                max="120"
                step="1"
                @input="updateFontScale(Number(($event.target as HTMLInputElement).value))"
              />
              <span class="slider-value">{{ settings.fontScale }}%</span>
            </div>
          </div>

          <label class="toggle-row">
            <div class="setting-copy">
              <h3>自动滚动消息</h3>
              <p>新消息到达时默认滚动到底部，适合连续对话。</p>
            </div>
            <input
              :checked="settings.autoScrollChat"
              class="toggle-input"
              type="checkbox"
              @change="updateBooleanSetting('autoScrollChat', ($event.target as HTMLInputElement).checked)"
            />
            <span class="toggle-slider"></span>
          </label>

          <label class="toggle-row">
            <div class="setting-copy">
              <h3>跳过输出动画</h3>
              <p>直接显示完整回复内容，不再等待逐字输出。</p>
            </div>
            <input
              :checked="settings.skipOutputAnimation"
              class="toggle-input"
              type="checkbox"
              @change="updateBooleanSetting('skipOutputAnimation', ($event.target as HTMLInputElement).checked)"
            />
            <span class="toggle-slider"></span>
          </label>

          <label class="toggle-row">
            <div class="setting-copy">
              <h3>默认开启调试模式</h3>
              <p>进入聊天页时默认显示工具消息，便于观察代理执行过程。</p>
            </div>
            <input
              :checked="settings.defaultDebugMode"
              class="toggle-input"
              type="checkbox"
              @change="updateBooleanSetting('defaultDebugMode', ($event.target as HTMLInputElement).checked)"
            />
            <span class="toggle-slider"></span>
          </label>
        </article>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive } from 'vue'
import {
  loadAppSettings,
  resetAppSettings,
  saveAppSettings,
  type AppSettings,
} from '../Services_/SettingsPageService'

type BooleanSettingKey = 'skipOutputAnimation' | 'autoScrollChat' | 'defaultDebugMode'

// 设置页直接使用本地持久化结果，避免依赖后端账户同步。
const settings = reactive<AppSettings>(loadAppSettings())

// 每次用户调整都立即保存，避免额外的“提交”步骤。
const persistSettings = () => {
  saveAppSettings({ ...settings })
}

const updateFontScale = (value: number) => {
  settings.fontScale = value
  persistSettings()
}

const updateBooleanSetting = (key: BooleanSettingKey, value: boolean) => {
  settings[key] = value
  persistSettings()
}

const resetSettings = () => {
  const resetValue = resetAppSettings()
  Object.assign(settings, resetValue)
}
</script>

<style scoped>
@import url('https://fonts.googleapis.com/css2?family=Cinzel:wght@500;600;700;800&family=UnifrakturMaguntia&family=Noto+Serif+SC:wght@400;500;600&display=swap');

.settings-page {
  min-height: 100%;
  background:
    linear-gradient(180deg, rgba(184, 138, 68, 0.04), transparent 16%),
    linear-gradient(180deg, #0b0b0d 0%, #101115 52%, #0d0d10 100%);
  color: #efe3c2;
}

.settings-shell {
  max-width: 1120px;
  margin: 0 auto;
  padding: 44px 42px 60px;
  position: relative;
}

.settings-shell::before {
  content: '';
  position: absolute;
  inset: 18px 0 0;
  pointer-events: none;
  opacity: 0.35;
  background-image:
    linear-gradient(90deg, transparent 0, transparent calc(50% - 1px), rgba(184, 138, 68, 0.08) calc(50% - 1px), rgba(184, 138, 68, 0.08) calc(50% + 1px), transparent calc(50% + 1px)),
    linear-gradient(180deg, transparent 0, rgba(184, 138, 68, 0.05) 48%, transparent 100%);
  background-size: 100% 100%, 100% 220px;
  background-repeat: no-repeat, repeat-y;
}

.settings-hero {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 28px;
  margin-bottom: 14px;
  padding: 10px 0 22px;
}

.eyebrow {
  margin: 0 0 8px;
  color: rgba(230, 213, 168, 0.5);
  text-transform: uppercase;
  letter-spacing: 2.4px;
  font-size: 0.68rem;
  line-height: 1;
}

.settings-hero h1 {
  margin: 0;
  font-family: 'Cinzel', 'UnifrakturMaguntia', 'Noto Serif SC', serif;
  font-size: 2.56rem;
  font-weight: 700;
  line-height: 1.06;
  letter-spacing: 2.6px;
  text-transform: uppercase;
  text-align: left;
  background: linear-gradient(135deg, #e6d5a8 0%, #b88a44 100%);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
  text-shadow: 2px 2px 5px rgba(0, 0, 0, 0.45);
  transform: skew(-1deg) rotate(-0.5deg);
}

.hero-copy-block {
  position: relative;
}

.hero-actions {
  display: flex;
  justify-content: flex-end;
}

.secondary-btn {
  min-width: 118px;
  height: 40px;
  border: 1px solid rgba(210, 180, 140, 0.24);
  background: linear-gradient(180deg, rgba(31, 31, 36, 0.92), rgba(21, 21, 24, 0.96));
  color: #f2ddb0;
  border-radius: 999px;
  cursor: pointer;
  box-shadow: 0 8px 20px rgba(0, 0, 0, 0.18);
  transition: all 0.2s ease;
  font-size: 0.9rem;
  letter-spacing: 0.3px;
}

.secondary-btn:hover {
  background: linear-gradient(180deg, rgba(42, 38, 31, 0.95), rgba(26, 24, 20, 0.98));
  border-color: rgba(210, 180, 140, 0.4);
  box-shadow: 0 0 8px rgba(184, 138, 68, 0.12);
  transform: translateY(-1px);
}

.settings-flow {
  position: relative;
  padding-top: 10px;
}

.settings-flow::before {
  content: '';
  position: absolute;
  inset: 0;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
  pointer-events: none;
}

.settings-section {
  padding: 24px 0 28px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  position: relative;
}

.settings-section::after {
  content: '';
  position: absolute;
  left: 0;
  bottom: -1px;
  width: 220px;
  height: 1px;
  background: linear-gradient(90deg, rgba(184, 138, 68, 0.32), rgba(184, 138, 68, 0.08), transparent 78%);
}

.card-header {
  margin-bottom: 16px;
  position: relative;
  padding-left: 16px;
}

.card-header::before {
  content: '';
  position: absolute;
  left: 0;
  top: 7px;
  width: 7px;
  height: 7px;
  transform: rotate(45deg);
  border: 1px solid rgba(184, 138, 68, 0.5);
  background: rgba(184, 138, 68, 0.1);
}

.card-kicker {
  margin: 0 0 6px;
  color: rgba(230, 213, 168, 0.46);
  text-transform: uppercase;
  letter-spacing: 1.5px;
  font-size: 0.68rem;
  line-height: 1.1;
}

.card-header h2 {
  margin: 0;
  font-family: 'Cinzel', 'Noto Serif SC', serif;
  font-size: 1.24rem;
  color: #f0ddb2;
  letter-spacing: 0.6px;
  line-height: 1.2;
}

.setting-item,
.toggle-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 24px;
  align-items: center;
  padding: 16px 0;
  border-top: 1px solid rgba(255, 255, 255, 0.05);
}

.setting-item:first-of-type,
.toggle-row:first-of-type {
  border-top: none;
  padding-top: 0;
}

.setting-copy h3 {
  margin: 0 0 6px;
  font-size: 1rem;
  font-weight: 600;
  line-height: 1.35;
  color: #f7e7bc;
}

.setting-copy p {
  margin: 0;
  color: rgba(239, 227, 194, 0.62);
  line-height: 1.58;
  font-size: 0.9rem;
  max-width: 42rem;
}

.slider-row {
  align-items: center;
}

.slider-control {
  display: flex;
  align-items: center;
  gap: 14px;
  min-width: 280px;
}

.range-slider {
  width: 220px;
  appearance: none;
  height: 4px;
  border-radius: 999px;
  background: linear-gradient(90deg, rgba(184, 138, 68, 0.8), rgba(255, 255, 255, 0.16));
  outline: none;
}

.range-slider::-webkit-slider-thumb {
  appearance: none;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: #f1dfb6;
  border: 1px solid rgba(115, 82, 36, 0.7);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.28);
  cursor: pointer;
}

.range-slider::-moz-range-thumb {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: #f1dfb6;
  border: 1px solid rgba(115, 82, 36, 0.7);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.28);
  cursor: pointer;
}

.slider-value {
  min-width: 48px;
  color: #f3e3ba;
  font-size: 0.92rem;
  text-align: right;
}

.toggle-row {
  position: relative;
  cursor: pointer;
}

.toggle-input {
  position: absolute;
  opacity: 0;
  pointer-events: none;
}

.toggle-slider {
  position: relative;
  width: 56px;
  height: 30px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(210, 180, 140, 0.1);
  transition: 0.2s ease;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.03);
}

.toggle-slider::after {
  content: '';
  position: absolute;
  top: 3px;
  left: 3px;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: #f4e4be;
  transition: 0.2s ease;
}

.toggle-input:checked + .toggle-slider {
  background: rgba(184, 138, 68, 0.35);
  border-color: rgba(230, 213, 168, 0.4);
}

.toggle-input:checked + .toggle-slider::after {
  transform: translateX(26px);
  background: #fff3d0;
}

@media (max-width: 680px) {
  .settings-shell {
    padding: 32px 18px 44px;
  }

  .settings-shell::before {
    display: none;
  }

  .settings-hero {
    flex-direction: column;
    align-items: flex-start;
  }

  .settings-hero h1 {
    font-size: 2.06rem;
    letter-spacing: 1.8px;
  }

  .setting-item,
  .toggle-row {
    grid-template-columns: 1fr;
  }

  .slider-control {
    min-width: 100%;
    width: 100%;
  }

  .range-slider {
    width: 100%;
  }
}
</style>
