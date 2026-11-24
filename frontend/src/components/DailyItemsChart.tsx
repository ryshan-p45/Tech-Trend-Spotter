import ReactEChartsCore from 'echarts-for-react/lib/core'
import * as echarts from 'echarts/core'
import { BarChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { SVGRenderer } from 'echarts/renderers'
import type { DailyCount } from '../api/types.ts'
import {
  CHART_AXIS_TEXT, CHART_GRID, CHART_SURFACE, CHART_TEXT, SOURCE_TYPE_COLORS, SOURCE_TYPE_ORDER,
} from '../lib/chartColors.ts'
import { SOURCE_TYPE_LABELS, shortDate } from '../lib/format.ts'

// Register only what this chart uses, so the bundle doesn't include all of ECharts
echarts.use([BarChart, GridComponent, LegendComponent, TooltipComponent, SVGRenderer])

type DailyItemsChartProps = {
  days: DailyCount[]
}

/*
 * Stacked columns: items per day, split by source type.
 *
 * Follows the dataviz mark specs: thin columns (max 24px), 4px rounded top only on the
 * top segment, a 2px gap in the surface colour between segments, hairline solid grid,
 * a legend (3 series) and an axis tooltip on hover. The same numbers are available as
 * a table under "View as table" for screen readers and anyone who prefers figures.
 */
function DailyItemsChart({ days }: DailyItemsChartProps) {
  const dates = days.map((day) => shortDate(day.date).replace(/ \d{4}$/, ''))
  const lastIndex = SOURCE_TYPE_ORDER.length - 1

  const option = {
    backgroundColor: 'transparent',
    textStyle: { fontFamily: 'JetBrains Mono, monospace', color: CHART_TEXT },
    grid: { left: 8, right: 8, top: 36, bottom: 8, containLabel: true },
    legend: {
      top: 0, left: 0, icon: 'roundRect', itemWidth: 10, itemHeight: 10,
      textStyle: { color: CHART_TEXT, fontSize: 11 },
    },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow', shadowStyle: { color: 'rgba(63, 216, 242, 0.06)' } },
      backgroundColor: CHART_SURFACE,
      borderColor: '#1e4a6b',
      textStyle: { color: CHART_TEXT, fontSize: 12 },
    },
    xAxis: {
      type: 'category',
      data: dates,
      axisLine: { lineStyle: { color: CHART_GRID } },
      axisTick: { show: false },
      axisLabel: { color: CHART_AXIS_TEXT, fontSize: 10 },
    },
    yAxis: {
      type: 'value',
      minInterval: 1,
      splitLine: { lineStyle: { color: CHART_GRID, width: 1, type: 'solid' } },
      axisLabel: { color: CHART_AXIS_TEXT, fontSize: 10 },
    },
    series: SOURCE_TYPE_ORDER.map((type, index) => ({
      name: SOURCE_TYPE_LABELS[type],
      type: 'bar',
      stack: 'items',
      barMaxWidth: 24,
      data: days.map((day) => day[type]),
      itemStyle: {
        color: SOURCE_TYPE_COLORS[type],
        borderColor: CHART_SURFACE, // surface-coloured edge = the 2px gap between segments
        borderWidth: 1,
        borderRadius: index === lastIndex ? [4, 4, 0, 0] : 0,
      },
      emphasis: { focus: 'series' },
    })),
  }

  const total = days.reduce((sum, day) => sum + day.web + day.social + day.advisory, 0)

  return (
    <div>
      <ReactEChartsCore echarts={echarts} option={option} style={{ height: 260 }} notMerge
        opts={{ renderer: 'svg' }} role="img"
        aria-label={`Items collected per day over the last ${days.length} days, ${total} in total, by source type`} />
      <details className="mt-3 text-xs text-hud-muted">
        <summary className="cursor-pointer select-none hover:text-hud-text">View as table</summary>
        <div className="mt-2 max-h-60 overflow-auto">
          <table className="w-full text-left tabular-nums">
            <thead>
              <tr className="text-hud-muted">
                <th scope="col" className="py-1 pr-4 font-normal">Date</th>
                {SOURCE_TYPE_ORDER.map((type) => (
                  <th key={type} scope="col" className="py-1 pr-4 font-normal">{SOURCE_TYPE_LABELS[type]}</th>
                ))}
              </tr>
            </thead>
            <tbody className="text-hud-text">
              {days.map((day) => (
                <tr key={day.date} className="border-t border-hud-border/40">
                  <th scope="row" className="py-1 pr-4 font-normal">{shortDate(day.date)}</th>
                  {SOURCE_TYPE_ORDER.map((type) => <td key={type} className="py-1 pr-4">{day[type]}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  )
}

export default DailyItemsChart
