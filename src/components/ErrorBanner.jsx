export default function ErrorBanner({ message, onDismiss }) {
  return (
    <div className="error-banner" role="alert">
      <span>{message}</span>
      <button onClick={onDismiss} aria-label="Dismiss">×</button>
    </div>
  )
}