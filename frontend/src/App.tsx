import { useEffect, useState } from "react";
import { BarChart3, Bell, CircleHelp, LayoutDashboard, SearchCheck, Settings, Shield } from "lucide-react";
import { AlertDetailView } from "./components/AlertDetailView";
import { Dashboard } from "./components/Dashboard";
import { HelpGovernancePage } from "./components/HelpGovernancePage";
import { SettingsPage, type ThemeMode } from "./components/SettingsPage";

type AppView = "dashboard" | "investigations" | "help" | "settings";

function readStoredTheme(): ThemeMode {
  const stored = window.localStorage.getItem("riskassess-theme");
  return stored === "dark" ? "dark" : "light";
}

export default function App() {
  const [selectedAlert, setSelectedAlert] = useState<string | null>(null);
  const [view, setView] = useState<AppView>("dashboard");
  const [theme, setTheme] = useState<ThemeMode>(() => readStoredTheme());

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    window.localStorage.setItem("riskassess-theme", theme);
  }, [theme]);

  const goTo = (next: AppView) => {
    setView(next);
    setSelectedAlert(null);
  };

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <span><Shield size={23} fill="currentColor" /></span>
          <div><strong>RiskAssess</strong><small>TrustSphere Bank</small></div>
        </div>
        <nav aria-label="Primary navigation">
          <button className={!selectedAlert && view === "dashboard" ? "active" : ""} onClick={() => goTo("dashboard")}>
            <LayoutDashboard size={19} /> Case command centre
          </button>
          <button className={!selectedAlert && view === "investigations" ? "active" : ""} onClick={() => goTo("investigations")}>
            <SearchCheck size={19} /> Investigations
          </button>
          <button type="button"><BarChart3 size={19} /> Risk analytics</button>
        </nav>
        <div className="sidebar__bottom">
          <button className={!selectedAlert && view === "help" ? "active" : ""} onClick={() => goTo("help")}>
            <CircleHelp size={18} /> Help & governance
          </button>
          <button className={!selectedAlert && view === "settings" ? "active" : ""} onClick={() => goTo("settings")}>
            <Settings size={18} /> Settings
          </button>
          <div className="analyst">
            <div>AR</div>
            <span><strong>Amelia Reyes</strong><small>Senior investigator</small></span>
            <Bell size={17} />
          </div>
        </div>
      </aside>
      <div className="content">
        {selectedAlert ? (
          <AlertDetailView alertId={selectedAlert} onBack={() => setSelectedAlert(null)} />
        ) : view === "help" ? (
          <HelpGovernancePage />
        ) : view === "settings" ? (
          <SettingsPage theme={theme} onThemeChange={setTheme} />
        ) : (
          <Dashboard onSelectAlert={setSelectedAlert} investigationsOnly={view === "investigations"} />
        )}
      </div>
    </div>
  );
}
