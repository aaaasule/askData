<script setup lang="ts">
import { NConfigProvider, zhCN, dateZhCN, type GlobalThemeOverrides } from 'naive-ui'

import AppShell from '@/components/AppShell.vue'

const themeOverrides: GlobalThemeOverrides = {
  common: {
    primaryColor: '#0F6E6B',
    primaryColorHover: '#14817D',
    primaryColorPressed: '#0C5856',
    primaryColorSuppl: '#C46B3A',
    borderRadius: '8px',
    fontFamily: '"Segoe UI", "PingFang SC", "Noto Sans SC", sans-serif',
  },
}
</script>

<template>
  <NConfigProvider :locale="zhCN" :date-locale="dateZhCN" :theme-overrides="themeOverrides">
    <AppShell />
  </NConfigProvider>
</template>
