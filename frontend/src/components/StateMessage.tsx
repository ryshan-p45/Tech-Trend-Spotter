type StateMessageProps = {
  kind: 'loading' | 'empty' | 'error'
  message: string
}

// Shared loading / empty / error message so every panel handles those states the same way
function StateMessage({ kind, message }: StateMessageProps) {
  const icon = { loading: '◌', empty: '○', error: '!' }[kind]
  const tone = kind === 'error' ? 'text-hud-danger' : 'text-hud-muted'
  return (
    <p role={kind === 'error' ? 'alert' : 'status'} className={`flex items-start gap-2 py-6 text-sm ${tone}`}>
      <span aria-hidden="true" className={kind === 'loading' ? 'animate-spin' : ''}>{icon}</span>
      <span>{message}</span>
    </p>
  )
}

export default StateMessage
