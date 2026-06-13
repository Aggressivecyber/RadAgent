import type { ShowcaseCard } from './homeSummary'

export type HomeLaunchTarget = {
  kind: 'example'
  exampleId: string
  prompt: string
}

export function createShowcaseLaunchTarget(example: ShowcaseCard): HomeLaunchTarget | null {
  const prompt = example.prompt.trim()
  if (!prompt) {
    return null
  }
  return { kind: 'example', exampleId: example.id, prompt }
}
