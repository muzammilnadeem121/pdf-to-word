import { useState, useCallback } from 'react'
import { uploadPdf, convertPdf, getDownloadUrl, ApiError } from '../api/client'

/**
 * Stages of the conversion pipeline, in order.
 * Mirrors the backend pipeline: upload -> extract/OCR -> repair -> layout -> export.
 */
export const Stage = {
  IDLE:       'idle',
  UPLOADING:  'uploading',
  CONVERTING: 'converting',
  DONE:       'done',
  ERROR:      'error',
}

export function useConversion() {
  const [stage, setStage]           = useState(Stage.IDLE)
  const [fileName, setFileName]     = useState(null)
  const [result, setResult]         = useState(null)
  const [error, setError]           = useState(null)

  const reset = useCallback(() => {
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

    setFileName(file.name)
    setError(null)

    try {
      // Stage 1 — Upload
      setStage(Stage.UPLOADING)
      const uploadResponse = await uploadPdf(file)

      // Stage 2 — Convert (extraction, OCR, repair, layout, export all
      // happen server-side inside this single call)
      setStage(Stage.CONVERTING)
      const convertResponse = await convertPdf(uploadResponse.fileId)

      setResult({
        downloadUrl:   getDownloadUrl(convertResponse.download_url),
        totalPages:    convertResponse.total_pages,
        digitalPages:  convertResponse.digital_pages,
        scannedPages:  convertResponse.scanned_pages,
        mixedPages:    convertResponse.mixed_pages,
      })
      setStage(Stage.DONE)

    } catch (err) {
      const message = err instanceof ApiError
        ? err.message
        : 'Something went wrong. Please try again.'
      setError(message)
      setStage(Stage.ERROR)
    }
  }, [])

  return { stage, fileName, result, error, convert, reset }
}