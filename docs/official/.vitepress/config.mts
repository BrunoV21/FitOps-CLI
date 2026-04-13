import { defineConfig } from 'vitepress'

export default defineConfig({
  title: "FitOps CLI",
  description: "CLI training analytics for runners and cyclists. Rich terminal output by default. Your data, your machine.",
  base: '/FitOps-CLI/',
  appearance: 'force-dark',

  head: [
    ['link', { rel: 'icon', href: '/FitOps-CLI/favicon.ico' }],
    ['link', { rel: 'preconnect', href: 'https://fonts.googleapis.com' }],
    ['link', { rel: 'preconnect', href: 'https://fonts.gstatic.com', crossorigin: '' }],
    ['link', { href: 'https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&display=swap', rel: 'stylesheet' }],
  ],

  themeConfig: {
    nav: [
      { text: 'Home', link: '/' },
      { text: 'Get Started', link: '/getting-started/' },
      { text: 'Commands', link: '/commands/' },
      { text: 'Concepts', link: '/concepts/' },
      { text: 'Dashboard', link: '/dashboard/' },
      { text: 'vs. Alternatives', link: '/comparison' },
      { text: 'Roadmap', link: '/roadmap' },
    ],

    sidebar: [
      {
        text: '// GETTING STARTED',
        items: [
          { text: 'Overview', link: '/getting-started/' },
          { text: 'Installation', link: '/getting-started/installation' },
          { text: 'Authentication', link: '/getting-started/authentication' },
          { text: 'First Sync', link: '/getting-started/first-sync' },
        ]
      },
      {
        text: '// COMMANDS',
        items: [
          { text: 'Overview', link: '/commands/' },
          { text: 'auth', link: '/commands/auth' },
          { text: 'sync', link: '/commands/sync' },
          { text: 'activities', link: '/commands/activities' },
          { text: 'athlete', link: '/commands/athlete' },
          { text: 'analytics', link: '/commands/analytics' },
          { text: 'weather', link: '/commands/weather' },
          { text: 'workouts', link: '/commands/workouts' },
          { text: 'race', link: '/commands/race' },
          { text: 'notes', link: '/commands/notes' },
          { text: 'backup', link: '/commands/backup' },
        ]
      },
      {
        text: '// CONCEPTS',
        items: [
          { text: 'Overview', link: '/concepts/' },
          { text: 'Training Load', link: '/concepts/training-load' },
          { text: 'HR Zones', link: '/concepts/zones' },
          { text: 'VO2max', link: '/concepts/vo2max' },
          { text: 'Weather & Pace', link: '/concepts/weather-pace' },
          { text: 'Workouts & Compliance', link: '/concepts/workouts' },
          { text: 'Race Simulation', link: '/concepts/race-simulation' },
          { text: 'Training Notes', link: '/concepts/notes' },
          { text: 'AI Agent Integration', link: '/concepts/llm-integration' },
        ]
      },
      {
        text: '// OUTPUT EXAMPLES',
        items: [
          { text: 'Overview', link: '/output-examples/' },
          { text: 'Activities', link: '/output-examples/activities' },
          { text: 'Analytics', link: '/output-examples/analytics' },
          { text: 'Athlete', link: '/output-examples/athlete' },
          { text: 'Weather', link: '/output-examples/weather' },
          { text: 'Workouts', link: '/output-examples/workouts' },
          { text: 'Race', link: '/output-examples/race' },
          { text: 'Notes', link: '/output-examples/notes' },
        ]
      },
      {
        text: '// DASHBOARD',
        items: [
          { text: 'Overview', link: '/dashboard/' },
          { text: 'Home (Overview page)', link: '/dashboard/overview' },
          { text: 'Activities', link: '/dashboard/activities' },
          { text: 'Analytics', link: '/dashboard/analytics' },
          { text: 'Workouts', link: '/dashboard/workouts' },
          { text: 'Race Planner', link: '/dashboard/race' },
          { text: 'Race Plans', link: '/dashboard/race-plans' },
          { text: 'Race Analysis', link: '/dashboard/race-analysis' },
          { text: 'Notes', link: '/dashboard/notes' },
          { text: 'Weather', link: '/dashboard/weather' },
          { text: 'Profile', link: '/dashboard/profile' },
          { text: 'Backup', link: '/dashboard/backup' },
        ]
      },
      {
        text: '// MORE',
        items: [
          { text: 'vs. Alternatives', link: '/comparison' },
          { text: 'Roadmap', link: '/roadmap' },
        ]
      },
    ],

    socialLinks: [
      { icon: 'github', link: 'https://github.com/BrunoV21/FitOps-CLI' }
    ],

    footer: {
      message: 'FitOps CLI — terminal-first training analytics',
    },

    search: {
      provider: 'local'
    },
  }
})
