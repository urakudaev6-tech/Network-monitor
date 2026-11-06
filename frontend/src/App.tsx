import { useEffect, useState } from "react";
import { SecurityLogin } from "./pages/SecurityLogin";
import { Route, Routes } from "react-router-dom";
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
    <Routes>
      <Route path="/login" element={<SecurityLogin />} />
      <Route path="/" element={<Dashboard />} />
      <Route path="/targets/:id" element={<TargetDetails />} />
      <Route path="/scanner" element={<NetworkScanner />} />
      <Route path="/scanner/devices" element={<DeviceRegistry />} />
      <Route path="/scanner/history" element={<NetworkHistory />} />
      <Route path="/alerts" element={<AlertCenter />} />
    </Routes>
  );
}
