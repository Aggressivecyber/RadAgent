export type ConfirmationReviewItem = {
  title: string
  detail: string
  meta: string
  fieldPath?: string
  recommendedValue?: string
}

export type ConfirmationParameterChecklistItem = {
  title: string
  value: string
  detail: string
  meta: string
  tone: 'confirmed' | 'needs-review'
  statusLabel: string
}

export type ConfirmationQuestionCard = {
  fieldPath: string
  question: string
  recommendedValue: string
  reason: string
}

export type ConfirmationQuestionAnswer = {
  mode: 'recommended' | 'modified'
  value: string
}

export type BuildQuestionCardSupplementOptions = {
  includeMachinePayload?: boolean
}

export type ConfirmationReviewView = {
  status: string
  actionable: boolean
  summary: string
  parameterChecklist: ConfirmationParameterChecklistItem[]
  missingInformation: string[]
  criticalConfirmations: ConfirmationReviewItem[]
  questions: ConfirmationReviewItem[]
  questionCards: ConfirmationQuestionCard[]
  proposedItems: ConfirmationReviewItem[]
  assumptions: string[]
  preview: string
}

export function buildQuestionCardSupplement(
  cards: ConfirmationQuestionCard[],
  answers: Record<string, ConfirmationQuestionAnswer>,
  freeformNote = '',
  options: BuildQuestionCardSupplementOptions = {},
): string {
  const lines: string[] = []
  const confirmedParameters: Record<string, string>[] = []
  for (const card of cards) {
    const answer = answers[card.fieldPath]
    if (!answer) {
      continue
    }
    const value = answer.value.trim()
    if (!value) {
      continue
    }
    const modeLabel = answer.mode === 'modified' ? '修改为' : '确认推荐'
    lines.push(`${card.fieldPath}: ${modeLabel} ${value}`)
    confirmedParameters.push({
      field_path: card.fieldPath,
      question: card.question,
      decision: answer.mode === 'modified' ? 'modify' : 'accept_recommended',
      selected_value: value,
      recommended_value: card.recommendedValue,
      reason: card.reason,
    })
  }
  const note = freeformNote.trim()
  if (note) {
    lines.push(`补充说明: ${note}`)
  }
  if (options.includeMachinePayload && confirmedParameters.length > 0) {
    lines.push(
      `RADAGENT_CONFIRMATION_JSON:${JSON.stringify({
        schema_version: 'requirements_review_answers_v1',
        confirmed_parameters: confirmedParameters,
        user_note: note,
      })}`,
    )
  }
  return lines.join('\n')
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
  const recommendedValue = summarizeValue(
    item.recommended_value ?? item.proposed_value ?? item.default_value,
  )
  return {
    title: text(item.question || item.field_path, `问题 ${index + 1}`),
    detail: text(item.impact || item.reason),
    meta: text(recommendedValue || item.category || item.field_path),
    fieldPath: text(item.field_path, `question.${index + 1}`),
    recommendedValue,
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

function confidenceMeta(value: unknown): string {
  return typeof value === 'number' && Number.isFinite(value) ? `${Math.round(value * 100)}%` : ''
}

function normalizedSourceType(value: unknown): string {
  return text(value).toLowerCase().replaceAll('-', '_')
}

function isExplicitSource(sourceType: string): boolean {
  return ['user', 'user_provided', 'explicit', 'confirmed', 'confirmed_by_user'].includes(sourceType)
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
  const confidence = confidenceMeta(item.confidence)
  return {
    title: text(item.field_path || item.scoring_id || item.source_id, `${fallbackLabel} ${index + 1}`),
    detail: text(item.reason || item.impact || summarizeValue(item.proposed_value)),
    meta: [sourceType, confidence].filter(Boolean).join(' · '),
  }
}

function fieldPathFromItem(item: Record<string, unknown>, fallbackLabel: string, index: number): string {
  return text(item.field_path || item.scoring_id || item.source_id || item.component_id, `${fallbackLabel} ${index + 1}`)
}

function parameterValueFromItem(item: Record<string, unknown>): string {
  return summarizeValue(
    item.proposed_value ??
      item.value ??
      item.default_value ??
      item.geometry ??
      item.dimensions ??
      item.placement ??
      item.material_id,
  )
}

function parameterRowFromItem(
  value: unknown,
  index: number,
  fallbackLabel: string,
  ambiguousByField: Map<string, Record<string, unknown>>,
  forceNeedsReview = false,
): ConfirmationParameterChecklistItem {
  const item = asRecord(value)
  const title = fieldPathFromItem(item, fallbackLabel, index)
  const ambiguous = ambiguousByField.get(title)
  const sourceType = text(item.source_type || item.source || item.category)
  const normalizedSource = normalizedSourceType(sourceType)
  const confidence = typeof item.confidence === 'number' ? item.confidence : null
  const needsReview =
    forceNeedsReview ||
    Boolean(item.requires_confirmation) ||
    Boolean(ambiguous) ||
    (Boolean(normalizedSource) && !isExplicitSource(normalizedSource)) ||
    (typeof confidence === 'number' && confidence < 0.9)

  return {
    title,
    value: parameterValueFromItem(item),
    detail: text(
      ambiguous?.reason ||
        ambiguous?.impact ||
        ambiguous?.question ||
        item.reason ||
        item.impact ||
        item.source_ref,
    ),
    meta: [sourceType, confidenceMeta(item.confidence)].filter(Boolean).join(' · '),
    tone: needsReview ? 'needs-review' : 'confirmed',
    statusLabel: needsReview ? 'AI 补全 / 需确认' : '明确',
  }
}

function parameterRowsFromProposal(
  proposal: Record<string, unknown>,
  ambiguousByField: Map<string, Record<string, unknown>>,
): ConfirmationParameterChecklistItem[] {
  const componentParameters = asArray(proposal.proposed_components).flatMap((component, componentIndex) => {
    const record = asRecord(component)
    const componentId = text(record.component_id, `组件 ${componentIndex + 1}`)
    return asArray(record.parameters).map((item, parameterIndex) =>
      parameterRowFromItem(item, parameterIndex, `${componentId} 参数`, ambiguousByField),
    )
  })

  return [
    ...asArray(proposal.proposed_parameters).map((item, index) =>
      parameterRowFromItem(item, index, '参数', ambiguousByField),
    ),
    ...componentParameters,
    ...asArray(proposal.proposed_sources).map((item, index) =>
      parameterRowFromItem(item, index, '源项', ambiguousByField),
    ),
    ...asArray(proposal.proposed_scoring).map((item, index) =>
      parameterRowFromItem(item, index, '输出', ambiguousByField),
    ),
  ]
}

function dedupeParameterRows(rows: ConfirmationParameterChecklistItem[]): ConfirmationParameterChecklistItem[] {
  const seen = new Set<string>()
  return rows.filter((row) => {
    const key = row.title
    if (!key || seen.has(key)) {
      return false
    }
    seen.add(key)
    return true
  })
}

function questionCardFromItem(value: unknown, index: number): ConfirmationQuestionCard {
  const item = asRecord(value)
  const fieldPath = text(item.field_path, `question.${index + 1}`)
  return {
    fieldPath,
    question: text(item.question || item.field_path, `请确认 ${fieldPath}`),
    recommendedValue: summarizeValue(
      item.recommended_value ?? item.proposed_value ?? item.default_value,
    ),
    reason: text(item.reason || item.impact || item.detail),
  }
}

function dedupeQuestionCards(cards: ConfirmationQuestionCard[]): ConfirmationQuestionCard[] {
  const seen = new Set<string>()
  return cards.filter((card) => {
    const key = `${card.fieldPath}\n${card.question}\n${card.recommendedValue}`
    if (seen.has(key)) {
      return false
    }
    seen.add(key)
    return true
  })
}

export function createConfirmationReviewView(data: unknown): ConfirmationReviewView {
  const review = asRecord(data)
  const requirementsReview = asRecord(review.requirements_review)
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
            title: '参数核对报告',
            detail: preview,
            meta: 'report',
          },
        ]
  const ambiguousFields = [
    ...asArray(review.ambiguous_fields),
    ...asArray(requirementsReview.ambiguous_parameters),
    ...asArray(requirementsReview.ambiguous_fields),
    ...asArray(request.ambiguous_fields),
    ...asArray(proposal.ambiguous_fields),
  ]
  const ambiguousByField = new Map(
    ambiguousFields
      .map((item, index) => {
        const record = asRecord(item)
        return [fieldPathFromItem(record, '模糊参数', index), record] as const
      })
      .filter(([field]) => Boolean(field)),
  )
  const parameterChecklist = dedupeParameterRows([
    ...parameterRowsFromProposal(proposal, ambiguousByField),
    ...asArray(requirementsReview.proposed_parameters).map((item, index) =>
      parameterRowFromItem(item, index, '参数', ambiguousByField),
    ),
    ...asArray(requirementsReview.proposed_defaults).map((item, index) =>
      parameterRowFromItem(item, index, '默认值', ambiguousByField, true),
    ),
    ...ambiguousFields.map((item, index) =>
      parameterRowFromItem(item, index, '模糊参数', ambiguousByField, true),
    ),
    ...asArray(review.critical_confirmations).map((item, index) =>
      parameterRowFromItem(item, index, '关键确认项', ambiguousByField, true),
    ),
    ...asArray(request.critical_confirmations).map((item, index) =>
      parameterRowFromItem(item, index, '关键确认项', ambiguousByField, true),
    ),
    ...asArray(review.questions).map((item, index) =>
      parameterRowFromItem(item, index, '问题', ambiguousByField, true),
    ),
    ...asArray(request.questions).map((item, index) =>
      parameterRowFromItem(item, index, '问题', ambiguousByField, true),
    ),
  ])
  const rawQuestions = [
    ...asArray(requirementsReview.questions),
    ...asArray(review.questions),
    ...asArray(request.questions),
  ]
  const questions = rawQuestions.map(itemFromQuestion)
  const questionCards = dedupeQuestionCards(rawQuestions.map(questionCardFromItem))

  return {
    status,
    actionable:
      typeof serverActionable === 'boolean'
        ? serverActionable
        : !['approved', 'rejected', 'failed', 'blocked'].includes(status),
    summary,
    parameterChecklist,
    missingInformation: [
      ...asArray(review.missing_information),
      ...asArray(requirementsReview.missing_information),
      ...asArray(request.missing_information),
      ...asArray(proposal.missing_information),
    ].map((item) => text(item)).filter(Boolean),
    criticalConfirmations: [
      ...asArray(review.critical_confirmations),
      ...asArray(request.critical_confirmations),
    ].map(itemFromCritical),
    questions,
    questionCards,
    proposedItems: proposedItemsWithFallback,
    assumptions: [
      ...asArray(review.assumptions),
      ...asArray(requirementsReview.physics_risks),
      ...asArray(request.assumptions),
      ...asArray(proposal.assumptions),
    ].map((item) => text(item)).filter(Boolean),
    preview,
  }
}
