import { Component } from "react";

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  render() {
    if (this.state.error) {
      return (
        <div className="min-h-[40vh] grid place-items-center p-8">
          <div className="card p-8 max-w-md text-center">
            <div className="text-lg font-semibold">Something went wrong</div>
            <p className="text-sm text-slate-500 mt-2">{String(this.state.error.message || this.state.error)}</p>
            <button className="btn-primary mt-4" onClick={() => window.location.reload()}>
              Reload
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
