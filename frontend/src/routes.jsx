import ViewerPage from "./pages/ViewerPage.jsx";
import DoubleTriggerPage from "./pages/DoubleTriggerPage.jsx";
import AboutPage from "./pages/AboutPage.jsx";

// ─────────────────────────────────────────────────────────────────────────────
//  ADD A PAGE HERE
//  1. Create a component in src/pages/YourPage.jsx
//  2. Import it above
//  3. Add an entry to this array: { path, label, element }
//  The nav bar and the router are both generated from this list, so a new
//  page shows up in the header automatically. Set `nav: false` to add a route
//  without a nav link.
// ─────────────────────────────────────────────────────────────────────────────
const routes = [
  { path: "/", label: "Viewer", element: <ViewerPage /> },
  { path: "/double-trigger", label: "Double Trigger", element: <DoubleTriggerPage /> },
  { path: "/about", label: "About", element: <AboutPage /> },
];

export default routes;
