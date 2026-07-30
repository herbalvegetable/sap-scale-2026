import { useState } from "react";
import { BarChart3, Bell, CircleHelp, LayoutDashboard, SearchCheck, Settings, Shield } from "lucide-react";
import { AlertDetailView } from "./components/AlertDetailView";
import { Dashboard } from "./components/Dashboard";

export default function App() {
  const [selectedAlert, setSelectedAlert] = useState<string | null>(null);

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <span><Shield size={23} fill="currentColor" /></span>
          <div><strong>RiskAssess</strong><small>TrustSphere Bank</small></div>
        </div>
        <nav aria-label="Primary navigation">
          <button className={!selectedAlert ? "active" : ""} onClick={() => setSelectedAlert(null)}>
            <LayoutDashboard size={19} /> Alert command centre
          </button>
          <button><BarChart3 size={19} /> Risk analytics</button>
        </nav>
        <div className="sidebar__bottom">
          <button><CircleHelp size={18} /> Help & governance</button>
          <button><Settings size={18} /> Settings</button>
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
        ) : (
          <Dashboard onSelectAlert={setSelectedAlert} />
        )}
      </div>
    </div>
  );
}
