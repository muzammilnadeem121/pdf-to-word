import { Stage, PIPELINE_STEPS } from '../hooks/useConversion'

export default function ProgressTracker({ stage, fileName }) {
  const currentIndex = PIPELINE_STEPS.findIndex(s => s.stage === stage)
  const pct = stage === Stage.DONE
    ? 100
    : PIPELINE_STEPS[currentIndex]?.pct ?? 0

  return (
    <div className="progress-tracker">

      <div className="progress-tracker__filename">
        <span className="progress-tracker__fileicon">📄</span>
        {fileName}
      </div>

      <ul className="progress-tracker__steps">
        {PIPELINE_STEPS.map((step, index) => {
          const isComplete = currentIndex > index || stage === Stage.DONE
          const isActive   = currentIndex === index

          return (
            <li
              key={step.stage}
              className={[
                'progress-tracker__step',
                isComplete && 'progress-tracker__step--complete',
                isActive   && 'progress-tracker__step--active',
              ].filter(Boolean).join(' ')}
            >
              <span className="progress-tracker__marker" aria-hidden="true">
                {isComplete ? '✓' : isActive ? '●' : '○'}
              </span>
              <span>{step.label}</span>
            </li>
          )
        })}
      </ul>

      <div className="progress-tracker__bar-wrap">
        <div className="progress-tracker__bar-bg">
          <div
            className="progress-tracker__bar-fill"
            style={{ width: `${pct}%` }}
            role="progressbar"
            aria-valuenow={pct}
            aria-valuemin={0}
            aria-valuemax={100}
          />
        </div>
        <span className="progress-tracker__pct">{pct}%</span>
      </div>

    </div>
  )
}