import { Route, Routes } from "react-router-dom";
import { Dashboard } from "./pages/Dashboard";
import { TargetDetails } from "./pages/TargetDetails";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Dashboard />} />
      <Route path="/targets/:id" element={<TargetDetails />} />
    </Routes>
  );
}