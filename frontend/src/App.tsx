import { Navigate, Route, Routes } from "react-router-dom";
import { RunConsole } from "./pages/RunConsole";
import { LeadExplorer } from "./pages/LeadExplorer";
import { LeadDetail } from "./pages/LeadDetail";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/run" replace />} />
      <Route path="/run" element={<RunConsole />} />
      <Route path="/leads" element={<LeadExplorer />} />
      <Route path="/leads/:id" element={<LeadDetail />} />
      <Route path="*" element={<Navigate to="/run" replace />} />
    </Routes>
  );
}
