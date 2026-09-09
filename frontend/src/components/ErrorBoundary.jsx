import { Component } from "react";

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    console.error("[Linkco MR]", error, info?.componentStack);
  }

  componentDidUpdate(prevProps) {
    if (this.props.resetKey !== prevProps.resetKey && this.state.error) {
      this.setState({ error: null });
    }
  }

  render() {
    if (this.state.error) {
      return (
        <div className="min-h-[40vh] grid place-items-center p-8">
          <div className="card p-8 max-w-md text-center">
            <div className="page-kicker mb-1">Workspace</div>
            <div className="text-lg font-semibold">Something went wrong</div>
            <p className="text-sm text-slate-500 mt-2">{String(this.state.error.message || this.state.error)}</p>
            <div className="mt-4 flex justify-center gap-2">
              <button className="btn-outline" onClick={() => this.setState({ error: null })}>
                Try again
              </button>
              <a className="btn-primary" href="/">
                Dashboard
              </a>
            </div>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
