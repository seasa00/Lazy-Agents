// Visual contract for the office scene.
// The 3D scene only ever receives this shape through props — it never owns workflow logic.
// In the real app an adapter (workflow events -> this contract) will sit in front of <OfficeCanvas />.

export const THEMES = ['day', 'night']

export const POSES = {
  manager: ['idle', 'thinking', 'assigning'],
  developer: ['idle', 'receiving', 'working', 'testing', 'submitting', 'blocked'],
  reviewer: ['idle', 'receiving', 'reviewing', 'pass', 'fail'],
}

export const initialOfficeState = {
  theme: 'day',
  reducedMotion: false,
  agents: {
    manager: { pose: 'thinking' },
    developer: { pose: 'working' },
    reviewer: { pose: 'idle' },
  },
}

// Handoff buttons in the dev panel are plain pose presets for now (no packets / travel yet).
export const handoffPresets = {
  managerToDeveloper: { manager: 'assigning', developer: 'receiving', reviewer: 'idle' },
  developerToReviewer: { manager: 'idle', developer: 'submitting', reviewer: 'receiving' },
  reviewFail: { manager: 'idle', developer: 'blocked', reviewer: 'fail' },
  reviewPass: { manager: 'thinking', developer: 'idle', reviewer: 'pass' },
}
