export type ConfirmationReviewItem = {
  title: string
  detail: string
  meta: string
}

export type ConfirmationReviewView = {
  status: string
  actionable: boolean
  summary: string
  missingInformation: string[]
  criticalConfirmations: ConfirmationReviewItem[]
  questions: ConfirmationReviewItem[]
  proposedItems: ConfirmationReviewItem[]
  assumptions: string[]
  preview: string
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {}
}

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : []
}

function text(value: unknown, fallback = ''): string {
  const normalized = String(value ?? '').trim()
  return normalized || fallback
}

function itemFromCritical(value: unknown, index: number): ConfirmationReviewItem {
  const item = asRecord(value)
  return {
    title: text(item.field_path, `确认项 ${index + 1}`),
    detail: text(item.impact || item.reason || item.proposed_value),
    meta: text(item.category || item.proposed_value),
  }
}

function itemFromQuestion(value: unknown, index: number): ConfirmationReviewItem {
  const item = asRecord(value)
  return {
    title: text(item.question || item.field_path, `问题 ${index + 1}`),
    detail: text(item.impact || item.reason),
    meta: text(item.proposed_value || item.category || item.field_path),
  }
}

function summarizeValue(value: unknown): string {
  if (value === null || value === undefined || value === '') {
    return ''
  }
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    return String(value)
  }
  try {
    return JSON.stringify(value)
  } catch {
    return String(value)
  }
}

function itemFromProposedComponent(value: unknown, index: number): ConfirmationReviewItem {
  const item = asRecord(value)
  const geometry = summarizeValue(item.geometry || item.dimensions || item.placement)
  const componentType = text(item.component_type, 'component')
  const material = text(item.material_id)
  return {
    title: text(item.component_id || item.display_name, `组件 ${index + 1}`),
    detail: geometry ? `几何/位置：${geometry}` : text(item.reason || item.roles),
    meta: [componentType, material].filter(Boolean).join(' · '),
  }
}

function itemFromProposedParameter(value: unknown, index: number, fallbackLabel: string): ConfirmationReviewItem {
  const item = asRecord(value)
  const sourceType = text(item.source_type || item.category)
  const confidence = typeof item.confidence === 'number' ? `${Math.round(item.confidence * 100)}%` : ''
  return {
    title: text(item.field_path || item.scoring_id || item.source_id, `${fallbackLabel} ${index + 1}`),
    detail: text(item.reason || item.impact || summarizeValue(item.proposed_value)),
    meta: [sourceType, confidence].filter(Boolean).join(' · '),
  }
}

export function createConfirmationReviewView(data: unknown): ConfirmationReviewView {
  const review = asRecord(data)
  const request = asRecord(review.confirmation_request || review.request)
  const proposal = asRecord(review.proposed_model_completion || review.proposal)
  const preview = text(review.preview)
  const summary = text(
    review.summary_for_user || request.summary_for_user || review.summary,
    '请确认本轮 Geant4 模型假设、关键参数和继续执行条件。',
  )
  const status = text(review.status, 'pending')
  const serverActionable = review.actionable
  const proposedItems = [
    ...asArray(proposal.proposed_components).map(itemFromProposedComponent),
    ...asArray(proposal.proposed_sources).map((item, index) =>
      itemFromProposedParameter(item, index, '源项'),
    ),
    ...asArray(proposal.proposed_scoring).map((item, index) =>
      itemFromProposedParameter(item, index, '输出'),
    ),
  ]
  const proposedItemsWithFallback =
    proposedItems.length > 0 || !preview
      ? proposedItems
      : [
          {
            title: '人工确认报告',
            detail: preview,
            meta: 'report',
          },
        ]

  return {
    status,
    actionable:
      typeof serverActionable === 'boolean'
        ? serverActionable
        : !['approved', 'rejected', 'failed', 'blocked'].includes(status),
    summary,
    missingInformation: [
      ...asArray(review.missing_information),
      ...asArray(request.missing_information),
      ...asArray(proposal.missing_information),
    ].map((item) => text(item)).filter(Boolean),
    criticalConfirmations: [
      ...asArray(review.critical_confirmations),
      ...asArray(request.critical_confirmations),
    ].map(itemFromCritical),
    questions: [
      ...asArray(review.questions),
      ...asArray(request.questions),
    ].map(itemFromQuestion),
    proposedItems: proposedItemsWithFallback,
    assumptions: [
      ...asArray(review.assumptions),
      ...asArray(request.assumptions),
      ...asArray(proposal.assumptions),
    ].map((item) => text(item)).filter(Boolean),
    preview,
  }
}
