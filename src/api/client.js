/**
 * API client for the Urdu PDF to Word converter backend.
 * Wraps the three pipeline endpoints: upload, convert, download.
 */

const BASE_URL = '' // empty — Vite proxy handles routing in dev

export class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function handleResponse(response) {
  if (!response.ok) {
    let detail = `Request failed with status ${response.status}`
    try {
      const body = await response.json()
      detail = body.detail || detail
    } catch {
      // response wasn't JSON — keep default message
    }
    throw new ApiError(detail, response.status)
  }
  return response.json()
}

/**
 * Upload a PDF file.
 * @param {File} file
 * @returns {Promise<{file_id: string}>}
 */
// src/api/client.js — update uploadPdf

export async function uploadPdf(file) {
  const formData = new FormData()
  formData.append('file', file)

  const response = await fetch(`${BASE_URL}/upload`, {
    method: 'POST',
    body: formData,
  })
  const data = await handleResponse(response)

  if (!data.stored_filename) {
    throw new ApiError(
      'Upload succeeded but no stored_filename was returned by the server.',
      response.status
    )
  }

  return { ...data, fileId: data.stored_filename }
}

/**
 * Convert a previously uploaded PDF to DOCX.
 * @param {string} fileId
 * @returns {Promise<{download_url: string, total_pages: number, digital_pages: number, scanned_pages: number, mixed_pages: number}>}
 */
export async function convertPdf(fileId) {
  const response = await fetch(`${BASE_URL}/convert/${encodeURIComponent(fileId)}`, {
    method: 'POST',
  })
  return handleResponse(response)
}

/**
 * Build the direct download URL for a converted file.
 * @param {string} downloadUrl - relative URL returned by convertPdf()
 * @returns {string}
 */
export function getDownloadUrl(downloadUrl) {
  return `${BASE_URL}${downloadUrl}`
}