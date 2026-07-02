import { useState, useCallback, useRef } from 'react'
import { uploadPdf, convertPdf, getDownloadUrl, ApiError } from '../api/client'

export const Stage = {
  IDLE:        'idle',
  UPLOADING:   'uploading',
  DETECTING:   'detecting',
  EXTRACTING:  'extracting',
  REPAIRING:   'repairing',
  LAYOUT:      'layout',
  EXPORTING:   'exporting',
  DONE:        'done',
  ERROR:       'error',
}

export const PIPELINE_STEPS = [
  { stage: Stage.UPLOADING,  label: 'Uploading PDF',            pct: 15 },
  { stage: Stage.DETECTING,  label: 'Detecting page types',     pct: 30 },
  { stage: Stage.EXTRACTING, label: 'Extracting text',          pct: 50 },
  { stage: Stage.REPAIRING,  label: 'Repairing Unicode & BiDi', pct: 65 },
  { stage: Stage.LAYOUT,     label: 'Detecting layout',         pct: 80 },
  { stage: Stage.EXPORTING,  label: 'Generating Word document', pct: 95 },
]

// How long to show each simulated stage while /convert runs (ms)
const STEP_INTERVAL = 2200

export function useConversion() {
  const [stage, setStage]       = useState(Stage.IDLE)
  const [fileName, setFileName] = useState(null)
  const [result, setResult]     = useState(null)
  const [error, setError]       = useState(null)
  const timerRef                = useRef(null)

  const clearTimer = () => {
    if (timerRef.current) clearInterval(timerRef.current)
  }

  const reset = useCallback(() => {
    clearTimer()
    setStage(Stage.IDLE)
    setFileName(null)
    setResult(null)
    setError(null)
  }, [])

  const convert = useCallback(async (file) => {
    if (!file) return

    if (file.type !== 'application/pdf') {
      setError('Please select a PDF file.')
      setStage(Stage.ERROR)
      return
    }

    clearTimer()
    setFileName(file.name)
    setError(null)

    const simulatedStages = [
      Stage.DETECTING,
      Stage.EXTRACTING,
      Stage.REPAIRING,
      Stage.LAYOUT,
      Stage.EXPORTING,
    ]

    try {
      // Stage 1 — Upload (real)
      setStage(Stage.UPLOADING)
      const uploadResponse = await uploadPdf(file)

      // Start the /convert request and the animation simultaneously
      const convertPromise = convertPdf(uploadResponse.fileId)

      // Animate through stages — each step shows for STEP_INTERVAL ms
      // We always show at least the first 2 steps regardless of server speed
      let stepIndex = 0
      setStage(simulatedStages[stepIndex])
      stepIndex++

      const animationPromise = new Promise((resolve) => {
        timerRef.current = setInterval(() => {
          if (stepIndex < simulatedStages.length) {
            setStage(simulatedStages[stepIndex])
            stepIndex++
          } else {
            clearInterval(timerRef.current)
            resolve()
          }
        }, STEP_INTERVAL)
      })

      // Wait for BOTH the server AND at least 2 animation steps
      // This guarantees the user sees progress even on fast connections
      const minDisplayTime = new Promise(r => setTimeout(r, STEP_INTERVAL * 2))

      const [convertResponse] = await Promise.all([
        convertPromise,
        minDisplayTime,
      ])

      // Let the animation finish naturally if it's still running
      await animationPromise

      clearTimer()
      setResult({
        downloadUrl:  getDownloadUrl(convertResponse.download_url),
        totalPages:   convertResponse.total_pages,
        digitalPages: convertResponse.digital_pages,
        scannedPages: convertResponse.scanned_pages,
        mixedPages:   convertResponse.mixed_pages,
      })
      setStage(Stage.DONE)

    } catch (err) {
      clearTimer()
      setError(err instanceof ApiError ? err.message : 'Something went wrong. Please try again.')
      setStage(Stage.ERROR)
    }
  }, [])

  return { stage, fileName, result, error, convert, reset }
}