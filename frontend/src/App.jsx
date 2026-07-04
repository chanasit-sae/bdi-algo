import { Routes, Route, NavLink } from "react-router-dom";
import routes from "./routes.jsx";

// App shell: a top nav generated from routes.jsx plus the routed page body.
// You normally never edit this file to add a page — edit routes.jsx instead.
export default function App() {
  return (
    <div className="app">
      <header className="topnav">
        <h1>Ventilator Safety Monitoring System</h1>
        <nav>
          {routes
            .filter((r) => r.nav !== false)
            .map((r) => (
              <NavLink
                key={r.path}
                to={r.path}
                end={r.path === "/"}
                className={({ isActive }) => (isActive ? "active" : "")}
              >
                {r.label}
              </NavLink>
            ))}
        </nav>
      </header>
      <Routes>
        {routes.map((r) => (
          <Route key={r.path} path={r.path} element={r.element} />
        ))}
      </Routes>
    </div>
  );
}
