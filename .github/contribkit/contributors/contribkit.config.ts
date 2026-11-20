import { defineConfig, tierPresets } from '@lizardbyte/contribkit'

export default defineConfig({
  tiers: [
    { title: 'Hatchlings', preset: tierPresets.base },
    { title: 'Waders', monthlyDollars: 12, preset: tierPresets.medium },
    { title: 'Bulls', monthlyDollars: 25, preset: tierPresets.large },
    { title: 'Herd Leaders', monthlyDollars: 50, preset: tierPresets.xl },
  ],
})
