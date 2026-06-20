/// <reference types="vite/client" />

declare module 'plotly.js-dist-min' {
  const Plotly: unknown
  export default Plotly
}

declare module 'react-plotly.js/factory' {
  import type { ComponentType } from 'react'

  export default function createPlotlyComponent(plotly: unknown): ComponentType<Record<string, unknown>>
}
