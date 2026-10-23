<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { ECharts, EChartsCoreOption } from 'echarts'

const props = defineProps<{
  title: string
  option: Record<string, unknown>
}>()

const host = ref<HTMLDivElement | null>(null)
let chart: ECharts | null = null

async function render() {
  if (!host.value) return
  const echarts = await import('echarts')
  if (!host.value) return
  if (!chart) chart = echarts.init(host.value)
  chart.setOption(props.option as EChartsCoreOption, true)
}

function resize() {
  chart?.resize()
}

onMounted(() => {
  render()
  window.addEventListener('resize', resize)
})

watch(() => props.option, render, { deep: true })

onBeforeUnmount(() => {
  window.removeEventListener('resize', resize)
  chart?.dispose()
  chart = null
})
</script>

<template>
  <figure class="chart-card">
    <figcaption>{{ title }}</figcaption>
    <div ref="host" class="chart-canvas"></div>
  </figure>
</template>
