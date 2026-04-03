import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import App from "../app/App";
import { AppChromeProvider } from "../contexts/AppChromeContext";
import { MonthProvider } from "../contexts/MonthContext";
import ReconciliationWorkbenchPage from "../pages/ReconciliationWorkbenchPage";

export function renderAppAt(pathname: string) {
  window.history.pushState({}, "", pathname);
  return render(<App />);
}

export function renderWorkbenchPage() {
  return render(
    <MemoryRouter>
      <AppChromeProvider>
        <MonthProvider>
          <ReconciliationWorkbenchPage />
        </MonthProvider>
      </AppChromeProvider>
    </MemoryRouter>,
  );
}
