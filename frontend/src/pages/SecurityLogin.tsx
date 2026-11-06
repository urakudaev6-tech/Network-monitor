import { useState } from "react";
export function SecurityLogin() {
 const [password,setPassword]=useState("");
 const [error,setError]=useState("");
 const [busy,setBusy]=useState(false);
 async function submit(e:React.FormEvent) {
  e.preventDefault();setBusy(true);setError("");
  try { const r=await fetch("/api/auth/login",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({password})});
    if(!r.ok) throw new Error("Неверный пароль или ошибка входа");
    window.location.assign("/");
  } catch(e) {setError(e instanceof Error?e.message:"Ошибка входа");} finally {setBusy(false);}
 }
 return <main style={{maxWidth:380,margin:"12vh auto",padding:24}}><h1>Network Monitor</h1><h2>Вход администратора</h2><form onSubmit={submit}><input type="password" autoComplete="current-password" placeholder="Пароль администратора" value={password} onChange={e=>setPassword(e.target.value)} required style={{width:"100%",padding:12,boxSizing:"border-box"}}/><button disabled={busy} style={{marginTop:16,padding:12,width:"100%"}}>Войти</button></form>{error&&<p role="alert">{error}</p>}</main>;
}
