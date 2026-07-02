import { useState, useCallback, useRef } from 'react'

/**
 * Drag-and-drop + click-to-browse file picker.
 * Only accepts PDFs. Calls onFileSelected with the chosen File object.
 */
export default function Dropzone({ onFileSelected, disabled }) {
  const [isDragging, setIsDragging] = useState(false)
  const inputRef = useRef(null)

  const handleDrop = useCallback((e) => {
    e.preventDefault()
    setIsDragging(false)
    if (disabled) return

    const file = e.dataTransfer.files?.[0]
    if (file) onFileSelected(file)
  }, [onFileSelected, disabled])

  const handleDragOver = useCallback((e) => {
    e.preventDefault()
    if (!disabled) setIsDragging(true)
  }, [disabled])

  const handleDragLeave = useCallback(() => {
    setIsDragging(false)
  }, [])

  const handleClick = useCallback(() => {
    if (!disabled) inputRef.current?.click()
  }, [disabled])

  const handleInputChange = useCallback((e) => {
    const file = e.target.files?.[0]
    if (file) onFileSelected(file)
    e.target.value = '' // allow re-selecting the same file
  }, [onFileSelected])

  return (
    <div
      className={`dropzone ${isDragging ? 'dropzone--active' : ''} ${disabled ? 'dropzone--disabled' : ''}`}
      onDrop={handleDrop}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onClick={handleClick}
      role="button"
      tabIndex={0}
    >
      <input
        ref={inputRef}
        type="file"
        accept="application/pdf"
        onChange={handleInputChange}
        style={{ display: 'none' }}
      />
      <div className="dropzone__icon">📄</div>
      <p className="dropzone__text">
        {isDragging
          ? 'Drop your Urdu PDF here'
          : 'Drag & drop an Urdu PDF, or click to browse'}
      </p>
      <p className="dropzone__hint">Supports digital, scanned, and mixed PDFs</p>
    </div>
  )
}