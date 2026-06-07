import PageRouteHost from "./PageRouteHost";
import { appPageRoutes } from "./pageRegistry";

export default function AppRouter() {
  return <PageRouteHost routes={appPageRoutes} />;
}
