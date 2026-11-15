import type { PlotlyLike } from '@simtest-js/funnel';

declare global {
  interface Window {
    Plotly?: PlotlyLike;
  }
}
