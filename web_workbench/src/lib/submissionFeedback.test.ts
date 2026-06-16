import { describe, expect, it } from 'vitest'
import { createSubmissionFeedback } from './submissionFeedback'

describe('submission feedback', () => {
  it('presents a neutral ready state before launch', () => {
    expect(createSubmissionFeedback({ status: 'idle' })).toEqual({
      tone: 'idle',
      title: '等待提交',
      detail: '输入仿真指令后启动工作流。',
    })
  })

  it('presents a running state with the submitted command name', () => {
    expect(createSubmissionFeedback({ status: 'running', command: 'run' })).toEqual({
      tone: 'running',
      title: '正在仿真',
      detail: 'Agent 正在执行仿真工作流，状态会同步到侧边栏。',
    })
  })

  it('presents paused, success and error states without leaking slash commands', () => {
    expect(createSubmissionFeedback({ status: 'paused' })).toEqual({
      tone: 'paused',
      title: '等待审查',
      detail: '工作流停在人工确认点，请在审查面板处理后继续。',
    })
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
