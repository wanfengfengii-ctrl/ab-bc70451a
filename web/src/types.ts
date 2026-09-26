export interface TraceResult {
  position: number
  x: number
  serial: number
  fitted: number
  deviation: number
}

export interface RestoreSuccess {
  feasible: true
  spacing: number
  start: number
  maxDeviation: number
  sumSquaredDeviations: number
  traces: TraceResult[]
  missing: number[]
}

export interface RestoreFailure {
  feasible: false
  failure: {
    trace: number
    x: number
    requiredTolerance: number
    previousSerialRange: [number, number]
    candidateSerialRange: [number, number]
    message: string
  }
}

export type RestoreResponse = RestoreSuccess | RestoreFailure

export interface RestoreRequestBody {
  xs: number[]
  maxMissing: number[]
  tolerance: number
}
