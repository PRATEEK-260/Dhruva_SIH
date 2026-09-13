import { useState } from 'react';
import { Menu, TriangleAlert, ShieldAlert, Clock, Waves, Wind, Navigation, Map, Target, QrCode, Volume2, WifiOff, CheckCircle2 } from 'lucide-react';
import { ScanView, speak } from './ScanView';
import type { Capsule } from '../shared/capsule/decode';
import type { Language } from '../shared/capsule/codebook';

/** Which verdict banner a decoded capsule should show.
 *
 * Exported and pure so it can be tested against the real RISK_CLASSES values
 * without a DOM: risk_class decodes to fields.ts's lowercase-with-underscore
 * form ("safe" | "caution" | "no_go" | "unknown"), matching
 * backend/dhruva/codec/fields.py exactly, NOT the uppercase display labels the
 * banners themselves show. Comparing against the display label was the exact
 * bug that made NO-GO render no banner, no override notice, and no PFZ
 * suppression at all — this helper is the one place that comparison happens.
 */
export function verdictOf(
  riskClass: Capsule["risk_class"] | undefined,
): "no_go" | "caution" | "safe" | null {
  if (riskClass === "no_go" || riskClass === "caution" || riskClass === "safe") return riskClass;
  return null;
}

export function BoatApp() {
  // setLang is unused until a language-switcher control is wired up; kept
  // rather than removed since Language is already plumbed through ScanView
  // and speak() below.
  const [lang, _setLang] = useState<Language>("ta");
  const [isScanning, setIsScanning] = useState(false);
  const [capsule, setCapsule] = useState<Capsule | null>(null);
  const [advisoryText, setAdvisoryText] = useState<string>("");
  const [degraded, setDegraded] = useState(false);
  
  // Date tracking for mockup purposes
  const scanTime = capsule ? new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : "--";

  const handleScan = (res: { payload: string, advisory: { text: string, degraded: boolean }, capsule: Capsule }) => {
    setCapsule(res.capsule);
    setAdvisoryText(res.advisory.text);
    setDegraded(res.advisory.degraded);
    setIsScanning(false);
    speak(res.advisory.text, lang);
  };

  const handleSpeak = () => {
    if (advisoryText) speak(advisoryText, lang);
  };

  const verdict = verdictOf(capsule?.risk_class);
  const isNoGo = verdict === "no_go";
  const isCaution = verdict === "caution";
  const isSafe = verdict === "safe";

  return (
    <div className="bg-gray-50 min-h-screen font-sans max-w-md mx-auto shadow-2xl overflow-hidden flex flex-col relative">
      {isScanning && (
        <ScanView lang={lang} onScan={handleScan} onClose={() => setIsScanning(false)} />
      )}

      {/* Header */}
      <header className="bg-dhruva-nav text-white p-4 flex items-center justify-between z-10">
        <div className="flex items-center gap-3">
          <Menu className="w-6 h-6" />
          <div>
            <h1 className="font-bold text-xl leading-none tracking-wide">DHRUVA</h1>
            <p className="text-[10px] text-gray-300 tracking-wider">ISRO PS 26176</p>
          </div>
        </div>
        <div className="flex flex-col items-end">
          <div className="flex items-center gap-1 border border-red-500 rounded px-2 py-0.5 mb-1">
            <WifiOff className="w-3 h-3 text-red-500" />
            <span className="text-[10px] font-bold text-red-500 tracking-widest">OFFLINE</span>
          </div>
          <p className="text-[10px] text-gray-300">GPS: LOCKED</p>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 overflow-y-auto p-4 pb-32">
        {!capsule ? (
          <div className="flex flex-col items-center justify-center h-full text-center p-6 opacity-50 mt-20">
            <QrCode className="w-24 h-24 mb-4 text-gray-400" />
            <h2 className="text-xl font-bold text-gray-700">No Data</h2>
            <p className="text-gray-500 mt-2">Scan a QR code from the boat receiver to get the latest advisory.</p>
          </div>
        ) : (
          <>
            {/* Verdict Card */}
            {isNoGo && (
              <div className="bg-danger text-white rounded-xl p-4 shadow-md mb-2">
                <div className="flex items-center gap-4 border-b border-red-700/50 pb-3 mb-3">
                  <TriangleAlert className="w-16 h-16 shrink-0" />
                  <div>
                    <h2 className="text-5xl font-black tracking-tight leading-none">NO-GO</h2>
                    <p className="text-lg font-semibold mt-1">Unsafe conditions</p>
                  </div>
                </div>
                <p className="text-sm font-medium">{advisoryText}</p>
              </div>
            )}
            
            {isCaution && (
              <div className="bg-caution text-white rounded-xl p-4 shadow-md mb-2">
                <div className="flex items-center gap-4 border-b border-orange-500/50 pb-3 mb-3">
                  <TriangleAlert className="w-16 h-16 shrink-0" />
                  <div>
                    <h2 className="text-5xl font-black tracking-tight leading-none">CAUTION</h2>
                    <p className="text-lg font-semibold mt-1">Proceed with care</p>
                  </div>
                </div>
                <p className="text-sm font-medium">{advisoryText}</p>
              </div>
            )}
            
            {isSafe && (
              <div className="bg-safe text-white rounded-xl p-4 shadow-md mb-2">
                <div className="flex items-center gap-4 border-b border-green-600/50 pb-3 mb-3">
                  <CheckCircle2 className="w-16 h-16 shrink-0" />
                  <div>
                    <h2 className="text-5xl font-black tracking-tight leading-none">SAFE</h2>
                    <p className="text-lg font-semibold mt-1">Favorable conditions</p>
                  </div>
                </div>
                <p className="text-sm font-medium">{advisoryText}</p>
              </div>
            )}

            {/* Override Notice */}
            {isNoGo && (
              <div className="bg-danger-light text-danger rounded-lg p-3 flex items-start gap-2 mb-4 border border-red-200">
                <ShieldAlert className="w-5 h-5 shrink-0 mt-0.5" />
                <p className="text-sm font-medium">Safety takes priority. Fishing zone data is suppressed.</p>
              </div>
            )}
            {degraded && (
              <div className="bg-caution-light text-caution rounded-lg p-3 flex items-start gap-2 mb-4 border border-orange-200">
                <ShieldAlert className="w-5 h-5 shrink-0 mt-0.5" />
                <p className="text-sm font-medium">Degraded signal. Data may be incomplete.</p>
              </div>
            )}

            {/* Data Age */}
            <div className="flex items-center gap-2 text-gray-600 mb-6 px-1">
              <Clock className="w-4 h-4" />
              <p className="text-sm">Data Age: <span className="font-medium text-gray-900">Updated {scanTime}</span></p>
            </div>

            {/* Sea Conditions */}
            <h3 className="font-bold text-gray-800 mb-3 px-1 uppercase tracking-wider text-sm">Sea Conditions</h3>
            <div className="grid grid-cols-3 gap-3 mb-6">
              <div className="bg-white rounded-xl p-3 shadow-sm border border-gray-100 flex flex-col items-center justify-center text-center">
                <Waves className="w-6 h-6 text-blue-500 mb-2" />
                <p className="text-[11px] font-semibold text-gray-500 uppercase tracking-wider mb-1">Wave Height</p>
                <p className="text-xl font-bold text-gray-900">{capsule.wave_hs_m.toFixed(1)} <span className="text-sm font-medium text-gray-500">m</span></p>
              </div>
              <div className="bg-white rounded-xl p-3 shadow-sm border border-gray-100 flex flex-col items-center justify-center text-center">
                <Wind className="w-6 h-6 text-blue-500 mb-2" />
                <p className="text-[11px] font-semibold text-gray-500 uppercase tracking-wider mb-1">Wind Speed</p>
                <p className="text-xl font-bold text-gray-900">{capsule.wind_kt} <span className="text-sm font-medium text-gray-500">kt</span></p>
              </div>
              <div className="bg-white rounded-xl p-3 shadow-sm border border-gray-100 flex flex-col items-center justify-center text-center">
                <Navigation className="w-6 h-6 text-blue-500 mb-2" />
                <p className="text-[11px] font-semibold text-gray-500 uppercase tracking-wider mb-1">Current</p>
                <p className="text-xl font-bold text-gray-900">{capsule.curr_kt.toFixed(1)} <span className="text-sm font-medium text-gray-500">kt</span></p>
              </div>
            </div>

            {/* Boundary Watch */}
            <div className={`bg-white rounded-xl p-4 shadow-sm border ${capsule.bnd_dist_nm < 2 ? 'border-red-200' : 'border-gray-200'} mb-6`}>
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <Map className="w-5 h-5 text-gray-700" />
                  <h3 className="font-bold text-gray-800 uppercase tracking-wider text-sm">Boundary Watch</h3>
                </div>
                {capsule.bnd_dist_nm < 2 && (
                  <span className="bg-danger text-white text-[10px] font-bold px-2 py-1 rounded-sm uppercase tracking-wider">Near Boundary</span>
                )}
              </div>
              <p className="text-sm text-gray-600 mb-3">{capsule.bnd_type === 'imbl' ? 'International Maritime Boundary Line (IMBL)' : 'Marine Protected Area (MPA)'}</p>
              <div className="flex gap-6">
                <div>
                  <p className={`text-3xl font-black ${capsule.bnd_dist_nm < 2 ? 'text-danger' : 'text-gray-900'}`}>{capsule.bnd_dist_nm.toFixed(1)} <span className="text-lg font-medium text-gray-600">NM <span className="text-sm">away</span></span></p>
                </div>
                {capsule.bnd_eta_min > 0 && capsule.bnd_eta_min < 255 && (
                  <div className="flex flex-col justify-end pb-1">
                    <p className="text-xs font-semibold text-gray-500 uppercase tracking-widest">ETA</p>
                    <p className="text-lg font-bold text-gray-900">{capsule.bnd_eta_min} min</p>
                  </div>
                )}
              </div>
            </div>

            {/* PFZ */}
            <div className={`bg-white rounded-xl p-4 shadow-sm border border-gray-200 ${isNoGo ? 'opacity-60 grayscale bg-gray-50' : ''}`}>
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <Target className="w-5 h-5 text-gray-700" />
                  <h3 className="font-bold text-gray-800 uppercase tracking-wider text-sm">Nearest Fishing Zone (PFZ)</h3>
                </div>
                {isNoGo && (
                  <span className="bg-gray-300 text-gray-700 text-[10px] font-bold px-2 py-1 rounded-sm uppercase tracking-wider">Suppressed</span>
                )}
              </div>
              <div className="flex gap-8 mb-3">
                <div>
                  <p className="text-xs font-semibold text-gray-500 uppercase tracking-widest mb-1">Distance</p>
                  <p className="text-2xl font-bold text-gray-900">{capsule.pfz_dist_nm.toFixed(1)} <span className="text-sm font-medium">NM</span></p>
                </div>
                <div>
                  <p className="text-xs font-semibold text-gray-500 uppercase tracking-widest mb-1">Bearing</p>
                  <p className="text-2xl font-bold text-gray-900">{capsule.pfz_bearing_deg}°</p>
                </div>
              </div>
              {isNoGo && (
                <p className="text-xs text-gray-500 font-medium bg-gray-100 p-2 rounded">ℹ Fishing zone data hidden due to NO-GO status.</p>
              )}
            </div>
          </>
        )}
      </main>

      {/* Sticky Bottom Actions */}
      <div className="absolute bottom-0 w-full bg-white border-t border-gray-200 p-4 pb-6 flex gap-3 shadow-[0_-4px_20px_rgba(0,0,0,0.05)] z-10">
        <button 
          onClick={() => setIsScanning(true)}
          className="flex-1 bg-blue-600 active:bg-blue-700 text-white rounded-xl p-3 flex flex-col items-center justify-center gap-1 min-h-[72px]"
        >
          <div className="flex items-center gap-2">
            <QrCode className="w-6 h-6" />
            <span className="font-bold text-lg">SCAN QR</span>
          </div>
          <span className="text-[11px] text-blue-100">Get Latest Advisory</span>
        </button>
        <button 
          onClick={handleSpeak}
          disabled={!capsule}
          className={`flex-1 rounded-xl p-3 flex flex-col items-center justify-center gap-1 min-h-[72px] ${!capsule ? 'bg-gray-300 text-gray-500' : 'bg-[#059669] active:bg-[#047857] text-white'}`}
        >
          <div className="flex items-center gap-2">
            <Volume2 className="w-6 h-6" />
            <span className="font-bold text-lg">SPEAK</span>
          </div>
          <span className="text-[11px] opacity-80">Play Voice Message</span>
        </button>
      </div>
    </div>
  );
}
