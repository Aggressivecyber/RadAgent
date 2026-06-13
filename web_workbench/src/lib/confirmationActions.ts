export function buildConfirmationCommand(): string {
  return '/confirm approve'
}

export function buildRejectCommand(reason: string): string {
  const trimmed = reason.trim()
  return trimmed ? `/reject ${trimmed}` : ''
}

export function buildAskMoreCommand(question: string): string {
  const trimmed = question.trim()
  return trimmed ? `/ask-more ${trimmed}` : ''
}
