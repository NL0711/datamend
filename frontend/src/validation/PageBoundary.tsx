// Catches a crash while a step page renders, so the visitor sees what happened and can go on, instead of a blank screen. It resets when the
// step changes (the ``resetKey``), and "Try again" re-renders the same page. The message is the error's own text; nothing is sent anywhere.
import { Component, type ErrorInfo, type ReactNode } from 'react';

interface Props { resetKey: string; children: ReactNode }
interface State { error: Error | null; key: string }

export class PageBoundary extends Component<Props, State> {
  state: State = { error: null, key: this.props.resetKey };

  static getDerivedStateFromError(error: Error): Partial<State> { return { error }; }

  static getDerivedStateFromProps(props: Props, state: State): Partial<State> | null {
    return props.resetKey !== state.key ? { error: null, key: props.resetKey } : null;     // a new step starts clean
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Page crashed:', error, info.componentStack);                             // stays in the browser console for debugging
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div role="alert" className="rounded-lg border border-red-300 bg-red-50 p-4 space-y-2 text-sm">
        <p className="font-bold text-red-800">This page hit an error and could not be shown.</p>
        <p className="text-xs text-red-700 font-mono break-words">{this.state.error.message}</p>
        <p className="text-xs text-slate-600">Your data is untouched. Try again, or open another page.</p>
        <button className="px-3 py-1.5 rounded border border-red-300 bg-white text-xs font-bold" onClick={() => this.setState({ error: null })}>Try again</button>
      </div>);
  }
}
