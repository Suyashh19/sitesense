import { Component } from 'react'
import type { ReactNode } from 'react'

/** Last line of defence: if any screen crashes, show a clear message and a reset button instead of a blank page. */
export class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null }
  static getDerivedStateFromError(error: Error) { return { error } }
  render() {
    if (!this.state.error) return this.props.children
    return (
      <div style={{ maxWidth: 640, margin: '60px auto', padding: 24, font: '15px/1.5 system-ui' }}>
        <h2>Something went wrong on this screen</h2>
        <p>Your data is safe — this is a display problem. Press the button to start again.</p>
        <p style={{ color: '#a02820' }}><b>Technical detail:</b> {this.state.error.message}</p>
        <button onClick={() => { this.setState({ error: null }); location.reload() }} style={{ padding: '10px 16px', fontWeight: 700 }}>Reload SiteSense</button>
      </div>
    )
  }
}
