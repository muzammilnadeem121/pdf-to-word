import { useConversion, Stage } from './hooks/useConversion'
import Dropzone from './components/Dropzone'
import ProgressTracker from './components/ProgressTracker'
import DownloadCard from './components/DownloadCard'
import ErrorBanner from './components/ErrorBanner'
import './index.css'

export default function App() {
  const { stage, fileName, result, error, convert, reset } = useConversion()

  const isBusy = stage !== Stage.IDLE && stage !== Stage.DONE && stage !== Stage.ERROR

  return (
    <div className="app">
      <header className="app__header">
        <h1>Urdu PDF → Word Converter</h1>
        <p>Convert digital, scanned, and mixed Urdu PDFs into editable Word documents.</p>
      </header>

      <main className="app__main">
        {error && (
          <ErrorBanner message={error} onDismiss={reset} />
        )}

        {stage === Stage.IDLE && (
          <Dropzone onFileSelected={convert} disabled={isBusy} />
        )}

        {isBusy && (
          <ProgressTracker stage={stage} fileName={fileName} />
        )}

        {stage === Stage.DONE && result && (
          <DownloadCard result={result} onConvertAnother={reset} />
        )}
      </main>
    </div>
  )
}