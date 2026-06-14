import { describe, expect, it } from 'vitest'
import { createSubmissionFeedback } from './submissionFeedback'

describe('submission feedback', () => {
  it('presents a neutral ready state before launch', () => {
    expect(createSubmissionFeedback({ status: 'idle' })).toEqual({
      tone: 'idle',
      title: '等待提交',
      detail: '选择任务模板、源项和材料后启动 Agent。',
    })
  })

  it('presents a running state with the submitted command name', () => {
    expect(createSubmissionFeedback({ status: 'running', command: 'run' })).toEqual({
      tone: 'running',
      title: '任务已提交',
      detail: '正在启动工作流，Agent 会先规划模型并写入时间线。',
    })
  })

  it('presents success and error states without leaking slash commands', () => {
    expect(createSubmissionFeedback({ status: 'success', command: 'run' })).toMatchObject({
      tone: 'success',
      title: '工作流已启动',
    })
    expect(createSubmissionFeedback({ status: 'error', message: 'API unavailable' })).toEqual({
      tone: 'error',
      title: '提交失败',
      detail: 'API unavailable',
    })
  })
})
