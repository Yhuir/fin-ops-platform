import { Component, type ReactNode } from "react";

import { reportRouteFailure } from "./routeDiagnostics";

type Props = { route: string; children: ReactNode };

export default class PageRouteErrorBoundary extends Component<Props, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error: Error) {
    reportRouteFailure("render", this.props.route, error);
  }

  render() {
    if (this.state.failed) {
      return (
        <section className="page-route-error" role="alert">
          <h1>页面暂时无法显示</h1>
          <button className="session-primary-action" type="button" onClick={() => window.location.reload()}>
            重新加载页面
          </button>
        </section>
      );
    }
    return this.props.children;
  }
}
