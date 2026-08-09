import { Navigate, useLocation } from "react-router-dom";

import PageRouteHost from "./PageRouteHost";
import { appPageRoutes } from "./pageRegistry";

export default function AppRouter() {
  const location = useLocation();
  if (location.pathname === "/imports" || location.pathname === "/imports/") {
    return <Navigate replace to="/imports/bank-transactions" />;
  }
  return <PageRouteHost routes={appPageRoutes} />;
}
