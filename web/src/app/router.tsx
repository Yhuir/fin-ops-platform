import PageKeepAliveHost from "./PageKeepAliveHost";
import { appPageRoutes } from "./pageRegistry";

export default function AppRouter() {
  return <PageKeepAliveHost routes={appPageRoutes} />;
}
