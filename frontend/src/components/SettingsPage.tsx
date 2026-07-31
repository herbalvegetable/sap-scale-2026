import { useState } from "react";
import { LogOut, Moon, Sun } from "lucide-react";
import { Button } from "./ui/button";

export type ThemeMode = "light" | "dark";

interface Props {
  theme: ThemeMode;
  onThemeChange: (theme: ThemeMode) => void;
}

export function SettingsPage({ theme, onThemeChange }: Props) {
  const [logoutNotice, setLogoutNotice] = useState(false);

  return (
    <main className="page-shell settings-page">
      <header className="page-header">
        <div>
          <p className="eyebrow">Workspace preferences</p>
          <h1>Settings</h1>
          <p>Adjust appearance for your investigation session. Changes apply immediately in this browser.</p>
        </div>
      </header>

      <section className="panel settings-card">
        <div className="panel__heading">
          <div>
            <p className="eyebrow">Appearance</p>
            <h2>Page theme</h2>
          </div>
        </div>
        <div className="settings-body">
          <p>Choose a light or dark theme for the RiskAssess workspace.</p>
          <div className="theme-toggle" role="group" aria-label="Theme">
            <button
              type="button"
              className={theme === "light" ? "active" : ""}
              onClick={() => onThemeChange("light")}
            >
              <Sun size={16} /> Light
            </button>
            <button
              type="button"
              className={theme === "dark" ? "active" : ""}
              onClick={() => onThemeChange("dark")}
            >
              <Moon size={16} /> Dark
            </button>
          </div>
        </div>
      </section>

      <section className="panel settings-card">
        <div className="panel__heading">
          <div>
            <p className="eyebrow">Session</p>
            <h2>Account</h2>
          </div>
        </div>
        <div className="settings-body">
          <p>
            Investigator demo session · AP-Southeast residency · no autonomous actions.
            Sign out ends this browser session; enterprise SSO is not wired in this build.
          </p>
          <Button
            variant="outline"
            onClick={() => {
              setLogoutNotice(true);
              window.setTimeout(() => setLogoutNotice(false), 2500);
            }}
          >
            <LogOut size={15} /> Log out
          </Button>
          {logoutNotice && (
            <p className="settings-notice" role="status">
              Signed out of the demo session. You can keep browsing locally.
            </p>
          )}
        </div>
      </section>
    </main>
  );
}
