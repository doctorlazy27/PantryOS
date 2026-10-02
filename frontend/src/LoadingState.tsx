export function LoadingState({ label = 'Loading warehouse data' }: { label?: string }) {
  return <div className="loading-screen" role="status" aria-live="polite">
    <span className="loading-spinner loading-spinner-large" aria-hidden="true" />
    <div className="loading-copy"><strong>{label}</strong><span>Syncing with the warehouse server</span></div>
    <div className="loading-skeleton" aria-hidden="true"><i /><i /><i /></div>
  </div>
}