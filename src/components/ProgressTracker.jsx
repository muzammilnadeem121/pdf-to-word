import { Stage } from '../hooks/useConversion'

const STEPS = [
  { stage: Stage.UPLOADING,  label: 'Uploading PDF' },
  { stage: Stage.CONVERTING, label: 'Extracting text, running OCR, and formatting' },
]

/**
 * Visual progress through the conversion pipeline.
 * Shows which stage is active, complete, or pending.
 */
export default function ProgressTracker({ stage, fileName }) {
  const currentIndex = STEPS.findIndex((s) => s.stage === stage)

  return (
    <div className="progress-tracker">
      <p className="progress-tracker__filename">{fileName}</p>
      <ul className="progress-tracker__steps">
        {STEPS.map((step, index) => {
          const isComplete = currentIndex > index || stage === Stage.DONE
          const isActive   = currentIndex === index

          return (
            <li
              key={step.stage}
              className={[
                'progress-tracker__step',
                isComplete && 'progress-tracker__step--complete',
                isActive && 'progress-tracker__step--active',
              ].filter(Boolean).join(' ')}
            >
              <span className="progress-tracker__marker">
                {isComplete ? '✓' : isActive ? '●' : '○'}
              </span>
              <span>{step.label}</span>
            </li>
          )
        })}
      </ul>
    </div>
  )
}