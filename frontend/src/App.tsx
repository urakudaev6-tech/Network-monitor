import { useEffect, useState } from "react";
import { SecurityLogin } from "./pages/SecurityLogin";
import { NavLink, Route, Routes } from "react-router-dom";
import { Dashboard } from "./pages/Dashboard";
import { TargetDetails } from "./pages/TargetDetails";
import { NetworkHistory } from "./pages/NetworkHistory";
import { DeviceRegistry } from "./pages/DeviceRegistry";
import { AlertCenter } from "./pages/AlertCenter"; // NM40_ALERT_CENTER_V1
import { NetworkScanner } from "./pages/NetworkScanner";

export default function App() {
  const [auth,setAuth]=useState<"checking"|"ok"|"login">("checking");
  useEffect(()=>{fetch("/api/auth/status").then(async r=>{
    if(!r.ok){setAuth("ok");return;}
    const d=await r.json();setAuth(d.enabled&&!d.authenticated?"login":"ok");
  }).catch(()=>setAuth("checking"));},[]);
  if(auth==="checking") return <main style={{padding:24}}>Проверка подключения к серверу...</main>;
  if(auth==="login") return <SecurityLogin/>;
  return (
    <div className="nm-app-shell"> {/* NM_PORTFOLIO_SHELL_V1 */}
      <aside className="nm-sidebar" aria-label="Главное меню">
        <div className="nm-brand"><span className="nm-brand-icon">◈</span><span>Network<span className="nm-brand-accent">Monitor</span><small>NETWORK OPERATIONS</small></span></div>
        <div className="nm-sidebar-label">РАБОЧАЯ ОБЛАСТЬ</div>
        <nav className="nm-sidebar-nav">
          <NavLink end to="/" className={({isActive}) => `nm-nav-link${isActive ? " active" : ""}`}><span>◫</span> Обзор</NavLink>
          <NavLink to="/scanner" end className={({isActive}) => `nm-nav-link${isActive ? " active" : ""}`}><span>⌁</span> Сканер сети</NavLink>
          <NavLink to="/scanner/devices" className={({isActive}) => `nm-nav-link${isActive ? " active" : ""}`}><span>▦</span> Реестр устройств</NavLink>
          <NavLink to="/scanner/history" className={({isActive}) => `nm-nav-link${isActive ? " active" : ""}`}><span>▤</span> История сети</NavLink>
          <NavLink to="/alerts" className={({isActive}) => `nm-nav-link${isActive ? " active" : ""}`}><span>◇</span> Центр уведомлений</NavLink>
        </nav>
        <div className="nm-sidebar-footer"><span className="nm-live-dot" /> Мониторинг сети <small>Network Monitor 4.1</small></div>
      </aside>
      <div className="nm-workspace">
        <header className="nm-topbar"><div><span className="nm-topbar-kicker">ПАНЕЛЬ УПРАВЛЕНИЯ</span><strong>Мониторинг и анализ сети</strong></div><span className="nm-topbar-version">Network Monitor · v4.1</span></header>
        <div className="nm-page-content">
    <Routes>
      <Route path="/login" element={<SecurityLogin />} />
      <Route path="/" element={<Dashboard />} />
      <Route path="/targets/:id" element={<TargetDetails />} />
      <Route path="/scanner" element={<NetworkScanner />} />
      <Route path="/scanner/devices" element={<DeviceRegistry />} />
      <Route path="/scanner/history" element={<NetworkHistory />} />
      <Route path="/alerts" element={<AlertCenter />} />
    </Routes>
        </div>
      </div>
    </div>
  );
}
