import { BrowserRouter, Routes, Route, Link, Navigate } from "react-router-dom";
import { BoatApp } from "./boat/BoatApp";
import { ShoreApp } from "./shore/ShoreApp";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/boat" element={<BoatApp />} />
        <Route path="/shore" element={<ShoreApp />} />
        <Route path="/" element={
          <div className="min-h-screen bg-gray-100 flex flex-col items-center justify-center p-4">
            <h1 className="text-3xl font-bold mb-8">Dhruva UIs</h1>
            <div className="flex gap-4">
              <Link to="/boat" className="px-6 py-3 bg-blue-600 text-white rounded-lg shadow-md hover:bg-blue-700">
                Launch Boat PWA (Mobile)
              </Link>
              <Link to="/shore" className="px-6 py-3 bg-slate-800 text-white rounded-lg shadow-md hover:bg-slate-900">
                Launch Shore Console (Desktop)
              </Link>
            </div>
          </div>
        } />
      </Routes>
    </BrowserRouter>
  );
}
