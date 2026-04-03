import { Component, type ReactNode } from 'react'

interface Props {
  children: ReactNode
  fallback?: ReactNode
}

interface State {
  hasError: boolean
  error?: Error
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false }

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error('[ErrorBoundary]', error, info.componentStack)
  }

  render() {
    if (this.state.hasError) {
      return this.props.fallback || (
        <div className="min-h-screen bg-surface flex items-center justify-center px-4">
          <div className="text-center max-w-sm">
            <div className="text-2xl mb-4 font-semibold">CrabRes</div>
            <h2 className="text-lg font-bold text-primary mb-2">Something went wrong</h2>
            <p className="text-sm text-muted mb-4">
              {this.state.error?.message || 'An unexpected error occurred'}
            </p>
            <button
              onClick={() => { this.setState({ hasError: false }); window.location.reload() }}
              className="btn-primary"
            >
              Reload
            </button>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}
