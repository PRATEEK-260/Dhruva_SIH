import { BrowserRouter, Routes, Route, Link } from "react-router-dom";
import { BoatApp } from "./boat/BoatApp";
import { ShoreApp } from "./shore/ShoreApp";
import { EmulatorApp } from "./emulator/EmulatorApp";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/boat" element={<BoatApp />} />
        <Route path="/shore" element={<ShoreApp />} />
        <Route path="/emulator" element={<EmulatorApp />} />
        <Route path="/" element={
          <div className="min-h-screen bg-gray-100 flex flex-col items-center justify-center p-4">
            <h1 className="text-3xl font-bold mb-8">Dhruva UIs</h1>
            <div className="flex flex-col gap-4 max-w-sm w-full">
              <Link to="/emulator" className="px-6 py-4 bg-green-600 text-white rounded-lg shadow-md hover:bg-green-700 text-center font-bold">
                1. Transponder Emulator (Online)
              </Link>
              <Link to="/boat" className="px-6 py-4 bg-blue-600 text-white rounded-lg shadow-md hover:bg-blue-700 text-center font-bold">
                2. Boat PWA (Offline Receiver)
              </Link>
              <Link to="/shore" className="px-6 py-4 bg-slate-800 text-white rounded-lg shadow-md hover:bg-slate-900 text-center font-bold">
                Launch Shore Console
              </Link>
            </div>
          </div>
        } />
      </Routes>
    </BrowserRouter>
  );
}
