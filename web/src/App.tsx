import { useState } from "react";
import { LangProvider, useLang } from "./lib/i18n";
import { Fleet } from "./views/Fleet";
import { Investigate } from "./views/Investigate";
import { Anomalies } from "./views/Anomalies";

type View = "fleet" | "inv" | "anom";

export function App() {
  return (
    <LangProvider>
      <Shell />
    </LangProvider>
  );
}

function Shell() {
  const { t, lang, setLang } = useLang();
  const [view, setView] = useState<View>("fleet");
  const [curDev, setCurDev] = useState<string | null>(null);
  const [live, setLive] = useState(false);
  const refreshMs = live ? 5000 : false;

  const openDevice = (id: string) => {
    setCurDev(id);
    setView("inv");
  };

  const tabs: { id: View; key: string }[] = [
    { id: "fleet", key: "nav_fleet" },
    { id: "inv", key: "nav_investigate" },
    { id: "anom", key: "nav_anomalies" },
  ];

  return (
    <>
      <div className="top">
        <div className="top-inner">
          <div className="brand">
            <span className="mk" aria-hidden="true">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
                <path d="M3 12h4l3 8 4-16 3 8h4" />
              </svg>
            </span>
            <span className="nm">
              sensor<span>line</span>
            </span>
          </div>
          <div className="tabs">
            {tabs.map((tb) => (
              <button
                key={tb.id}
                className="tab"
                type="button"
                aria-current={view === tb.id}
                onClick={() => setView(tb.id)}
              >
                {t(tb.key)}
              </button>
            ))}
          </div>
          <div className="seg langseg" role="group" aria-label="Language">
            <button type="button" aria-pressed={lang === "en"} onClick={() => setLang("en")}>
              EN
            </button>
            <button type="button" aria-pressed={lang === "de"} onClick={() => setLang("de")}>
              DE
            </button>
          </div>
        </div>
      </div>

      <main>
        {view === "fleet" && (
          <Fleet live={live} setLive={setLive} refreshMs={refreshMs} onOpenDevice={openDevice} />
        )}
        {view === "inv" && <Investigate deviceId={curDev} refreshMs={refreshMs} />}
        {view === "anom" && <Anomalies refreshMs={refreshMs} onOpenDevice={openDevice} />}
      </main>
    </>
  );
}
