import { useState } from 'react';
import QRCode from 'qrcode';
import { Wifi, Radio, QrCode } from 'lucide-react';
import { postAdvisory } from '../shared/api/client';
import type { Language } from '../shared/capsule/codebook';

const DEFAULT_LAT = 11.05;
const DEFAULT_LON = 79.95;

async function generateHandoffQr(capsuleBase32: string): Promise<string> {
  return QRCode.toString(capsuleBase32, { type: "svg" });
}

export function EmulatorApp() {
  const [askText, setAskText] = useState("");
  const [asking, setAsking] = useState(false);
  const [askError, setAskError] = useState<string | null>(null);
  const [qrSvg, setQrSvg] = useState<string | null>(null);
  const [userLat, setUserLat] = useState<string>(DEFAULT_LAT.toString());
  const [userLon, setUserLon] = useState<string>(DEFAULT_LON.toString());
  const [lang, setLang] = useState<Language>("ta");

  const handleAsk = async () => {
    if (!askText.trim()) return;
    setAsking(true);
    setAskError(null);
    try {
      const latNum = parseFloat(userLat);
      const lonNum = parseFloat(userLon);
      if (isNaN(latNum) || isNaN(lonNum)) throw new Error("Invalid coordinates");
      
      const response = await postAdvisory({
        query: askText,
        lat: latNum,
        lon: lonNum,
        language: lang,
        boat_class: "frp_under_12m",
      });
      
      setQrSvg(await generateHandoffQr(response.capsule_base32));
    } catch (e: any) {
      setAskError(e.message === "Invalid coordinates" ? "Please enter valid numbers for Lat/Lon" : "Network Error. Backend might be down.");
    } finally {
      setAsking(false);
    }
  };

  return (
    <div className="bg-slate-900 min-h-screen font-sans max-w-2xl mx-auto shadow-2xl overflow-hidden flex flex-col text-slate-200">
      <header className="bg-slate-950 text-white p-4 flex items-center justify-between border-b border-slate-800 shrink-0">
        <div className="flex items-center gap-3">
          <Radio className="w-6 h-6 text-green-400" />
          <div>
            <h1 className="font-bold text-xl leading-none tracking-wide">ISRO SATELLITE TRANSPONDER</h1>
            <p className="text-[10px] text-slate-400 tracking-wider">ONBOARD RECEIVER EMULATOR</p>
          </div>
        </div>
        <div className="flex items-center gap-1 border border-green-500 rounded px-2 py-0.5">
          <Wifi className="w-3 h-3 text-green-500" />
          <span className="text-[10px] font-bold text-green-500 tracking-widest">ONLINE</span>
        </div>
      </header>

      <div className="p-6 flex-1 flex flex-col">
        <div className="bg-slate-800 rounded-xl p-4 shadow-lg border border-slate-700 mb-6">
          <h2 className="text-sm font-bold text-slate-400 uppercase tracking-wider mb-4 border-b border-slate-700 pb-2">GPS & Location</h2>
          <div className="flex gap-4">
            <div className="flex-1">
              <label className="block text-xs text-slate-500 mb-1">Latitude</label>
              <input type="text" value={userLat} onChange={e => setUserLat(e.target.value)} className="w-full bg-slate-900 border border-slate-700 rounded px-3 py-2 text-sm focus:outline-none focus:border-green-500" />
            </div>
            <div className="flex-1">
              <label className="block text-xs text-slate-500 mb-1">Longitude</label>
              <input type="text" value={userLon} onChange={e => setUserLon(e.target.value)} className="w-full bg-slate-900 border border-slate-700 rounded px-3 py-2 text-sm focus:outline-none focus:border-green-500" />
            </div>
          </div>
        </div>

        <div className="bg-slate-800 rounded-xl p-4 shadow-lg border border-slate-700 mb-6">
          <h2 className="text-sm font-bold text-slate-400 uppercase tracking-wider mb-4 border-b border-slate-700 pb-2">Send Two-Way Request</h2>
          <div className="flex gap-3 mb-4">
            <input
              type="text"
              value={askText}
              onChange={(e) => setAskText(e.target.value)}
              placeholder="e.g. Is it safe to fish here?"
              className="flex-1 bg-slate-900 border border-slate-700 rounded px-3 py-2 text-sm focus:outline-none focus:border-green-500"
              disabled={asking}
            />
            <select 
              value={lang} 
              onChange={(e) => setLang(e.target.value as Language)}
              className="bg-slate-900 text-slate-200 text-sm px-3 py-2 rounded border border-slate-700 focus:outline-none"
            >
              <option value="en">English</option>
              <option value="ta">Tamil</option>
              <option value="hi">Hindi</option>
            </select>
          </div>
          <button
            onClick={handleAsk}
            disabled={asking || !askText.trim()}
            className="w-full py-3 bg-green-600 hover:bg-green-700 text-white rounded-lg text-sm font-bold disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {asking ? "TRANSMITTING TO SHORE..." : "TRANSMIT REQUEST"}
          </button>
          {askError && <p className="text-xs text-red-400 mt-2">{askError}</p>}
        </div>

        {qrSvg && (
          <div className="bg-slate-800 rounded-xl p-6 shadow-lg border border-green-500/50 flex flex-col items-center justify-center mt-auto">
            <h2 className="text-sm font-bold text-green-400 uppercase tracking-widest mb-2 flex items-center gap-2">
              <QrCode className="w-4 h-4" /> INCOMING CAPSULE
            </h2>
            <p className="text-xs text-slate-400 mb-6 text-center max-w-xs">A 145-bit compressed advisory has been received from shore. Scan this with the offline Boat App.</p>
            <div className="bg-white p-4 rounded-xl shadow-inner">
              <div className="w-64 h-64 [&>svg]:w-full [&>svg]:h-full" dangerouslySetInnerHTML={{ __html: qrSvg }} />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
