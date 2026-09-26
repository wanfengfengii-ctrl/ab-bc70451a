import { useState } from 'react'
import { restoreGrid } from './api'
import type { RestoreResponse, RestoreSuccess } from './types'

const MIN_ROWS = 5
const MAX_ROWS = 10

/** Format a number with up to 6 decimals, trimming trailing zeros. */
function fmt(v: number): string {
  if (!Number.isFinite(v)) return String(v)
  return String(Number(v.toFixed(6)))
}

export default function App() {
  const [xs, setXs] = useState<string[]>(['0', '10', '21', '31', '40'])
  const [maxMissing, setMaxMissing] = useState<string[]>(['1', '1', '1', '1'])
  const [tolerance, setTolerance] = useState<string>('0.5')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<RestoreResponse | null>(null)

  const updateX = (i: number, value: string) =>
    setXs((prev) => prev.map((v, j) => (j === i ? value : v)))

  const updateMissing = (i: number, value: string) =>
    setMaxMissing((prev) => prev.map((v, j) => (j === i ? value : v)))

  const addRow = () => {
    if (xs.length >= MAX_ROWS) return
    setXs((prev) => [...prev, ''])
    setMaxMissing((prev) => [...prev, '1'])
  }

  const removeRow = () => {
    if (xs.length <= MIN_ROWS) return
    setXs((prev) => prev.slice(0, -1))
    setMaxMissing((prev) => prev.slice(0, -1))
  }

  const validate = (): { xs: number[]; maxMissing: number[]; tolerance: number } => {
    const parsedXs = xs.map((s) => s.trim())
    if (parsedXs.some((s) => !/^-?\d+$/.test(s))) {
      throw new Error('每条残迹的横坐标必须是整数')
    }
    const nums = parsedXs.map(Number)
    for (let i = 1; i < nums.length; i += 1) {
      if (nums[i] <= nums[i - 1]) {
        throw new Error(`横坐标必须严格递增：第 ${i} 条与第 ${i + 1} 条冲突`)
      }
    }
    const parsedM = maxMissing.map((s) => s.trim())
    if (parsedM.some((s) => !/^\d+$/.test(s))) {
      throw new Error('相邻缺线数上限必须是非负整数')
    }
    const ms = parsedM.map(Number)
    if (ms.some((m) => m > 50)) {
      throw new Error('相邻缺线数上限不能超过 50')
    }
    const tol = Number(tolerance)
    if (!Number.isFinite(tol) || tol <= 0) {
      throw new Error('允许定位误差必须是正数')
    }
    return { xs: nums, maxMissing: ms, tolerance: tol }
  }

  const onSubmit = async () => {
    setError(null)
    setResult(null)
    let body
    try {
      body = validate()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      return
    }
    setLoading(true)
    try {
      setResult(await restoreGrid(body))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="page">
      <header>
        <h1>航海图经线网复原</h1>
        <p>
          录入受潮航海图上按从左到右的 5–10 条经线残迹，系统将把它们联合复原为同一套经线网：
          共同确定严格递增的经线序号、正的共同网距与起始位置，依次使最大偏差最小、
          偏差平方和最小、相邻缺线数序列字典序最小。
        </p>
      </header>

      <section className="panel">
        <h2>残迹录入</h2>
        <table className="input-table">
          <thead>
            <tr>
              <th>残迹</th>
              <th>整数横坐标 x</th>
              <th>与下一条之间最多缺线数</th>
            </tr>
          </thead>
          <tbody>
            {xs.map((x, i) => (
              <tr key={i}>
                <td>第 {i + 1} 条</td>
                <td>
                  <input
                    value={x}
                    inputMode="numeric"
                    onChange={(e) => updateX(i, e.target.value)}
                    placeholder="整数横坐标"
                  />
                </td>
                <td>
                  {i < xs.length - 1 ? (
                    <input
                      value={maxMissing[i]}
                      inputMode="numeric"
                      onChange={(e) => updateMissing(i, e.target.value)}
                      placeholder="0–50"
                    />
                  ) : (
                    <span className="muted">—</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="row-actions">
          <button type="button" onClick={addRow} disabled={xs.length >= MAX_ROWS}>
            增加残迹
          </button>
          <button type="button" onClick={removeRow} disabled={xs.length <= MIN_ROWS}>
            删除末条
          </button>
          <span className="muted">
            已录入 {xs.length} 条（{MIN_ROWS}–{MAX_ROWS} 条）
          </span>
        </div>
        <div className="tolerance-row">
          <label htmlFor="tolerance">允许定位误差</label>
          <input
            id="tolerance"
            value={tolerance}
            onChange={(e) => setTolerance(e.target.value)}
            placeholder="例如 0.5"
          />
          <button className="primary" type="button" onClick={onSubmit} disabled={loading}>
            {loading ? '复原中…' : '复原'}
          </button>
        </div>
      </section>

      {error && <div className="alert error">{error}</div>}

      {result && !result.feasible && (
        <div className="alert failure">
          <h2>无法复原为同一套经线网</h2>
          <p>{result.failure.message}</p>
          <dl>
            <dt>首个无法满足误差约束的残迹</dt>
            <dd>
              第 {result.failure.trace} 条（x = {result.failure.x}）
            </dd>
            <dt>相邻已定序号区间</dt>
            <dd>
              [{result.failure.previousSerialRange[0]},{' '}
              {result.failure.previousSerialRange[1]}]
            </dd>
            <dt>该残迹候选序号区间</dt>
            <dd>
              [{result.failure.candidateSerialRange[0]},{' '}
              {result.failure.candidateSerialRange[1]}]
            </dd>
            <dt>所需最小定位误差</dt>
            <dd>{fmt(result.failure.requiredTolerance)}</dd>
          </dl>
        </div>
      )}

      {result && result.feasible && <SuccessView result={result} />}
    </div>
  )
}

function SuccessView({ result }: { result: RestoreSuccess }) {
  return (
    <section className="panel">
      <h2>复原结果</h2>
      <div className="summary">
        <div>
          <span className="label">共同网距 d</span>
          <strong>{fmt(result.spacing)}</strong>
        </div>
        <div>
          <span className="label">起始位置 s（1 号经线）</span>
          <strong>{fmt(result.start)}</strong>
        </div>
        <div>
          <span className="label">最大偏差</span>
          <strong>{fmt(result.maxDeviation)}</strong>
        </div>
        <div>
          <span className="label">偏差平方和</span>
          <strong>{fmt(result.sumSquaredDeviations)}</strong>
        </div>
      </div>
      <table className="result-table">
        <thead>
          <tr>
            <th>残迹</th>
            <th>录入横坐标</th>
            <th>经线序号</th>
            <th>拟合位置</th>
            <th>偏差</th>
            <th>与下一条间补出缺线数</th>
          </tr>
        </thead>
        <tbody>
          {result.traces.map((t, i) => (
            <tr key={t.position}>
              <td>第 {t.position} 条</td>
              <td>{t.x}</td>
              <td>{t.serial}</td>
              <td>{fmt(t.fitted)}</td>
              <td className={Math.abs(t.deviation) > 1e-9 ? 'dev' : ''}>
                {t.deviation > 0 ? '+' : ''}
                {fmt(t.deviation)}
              </td>
              <td>{i < result.missing.length ? result.missing[i] : '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <GridChart result={result} />
    </section>
  )
}

/** Observed traces vs. the restored meridian grid (missing lines dashed). */
function GridChart({ result }: { result: RestoreSuccess }) {
  const width = 760
  const height = 150
  const pad = 36
  const maxSerial = Math.max(...result.traces.map((t) => t.serial))
  const positions = Array.from({ length: maxSerial }, (_, i) => ({
    serial: i + 1,
    pos: result.start + i * result.spacing,
  }))
  const observed = new Map(result.traces.map((t) => [t.serial, t]))
  const lo = Math.min(...result.traces.map((t) => t.x), positions[0].pos)
  const hi = Math.max(...result.traces.map((t) => t.x), positions[positions.length - 1].pos)
  const span = hi - lo || 1
  const px = (v: number) => pad + ((v - lo) / span) * (width - 2 * pad)

  return (
    <figure className="chart">
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="复原经线网示意图">
        <line x1={pad} y1={height - 30} x2={width - pad} y2={height - 30} className="axis" />
        {positions.map(({ serial, pos }) => {
          const obs = observed.get(serial)
          const x = px(pos)
          return (
            <g key={serial}>
              <line
                x1={x}
                y1={24}
                x2={x}
                y2={height - 30}
                className={obs ? 'grid-line' : 'grid-line missing'}
              />
              <text x={x} y={16} textAnchor="middle" className="tick-label">
                {serial}
              </text>
              {obs && (
                <>
                  <line
                    x1={px(obs.x)}
                    y1={height - 44}
                    x2={px(obs.x)}
                    y2={height - 16}
                    className="observed"
                  />
                  <text x={px(obs.x)} y={height - 4} textAnchor="middle" className="obs-label">
                    {obs.x}
                  </text>
                </>
              )}
            </g>
          )
        })}
      </svg>
      <figcaption>
        <span className="legend solid" /> 补全后的经线（序号见上方）
        <span className="legend dashed" /> 补出的缺失经线
        <span className="legend red" /> 实际残迹（横坐标见下方）
      </figcaption>
    </figure>
  )
}
