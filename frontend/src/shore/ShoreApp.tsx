import React from 'react';
import { 
  Ship, Map as MapIcon, Radio, BarChart2, Settings, Search, 
  ChevronRight, Calendar, Layers, Maximize, Plus, Minus,
  Thermometer, Leaf, Waves, Target, CheckCircle2, AlertTriangle, Info, Send
} from 'lucide-react';
import ReactMapGL, { MapProvider, Marker } from 'react-map-gl';
import 'maplibre-gl/dist/maplibre-gl.css';

export function ShoreApp() {
  return (
    <div className="flex h-screen bg-gray-100 font-sans overflow-hidden text-gray-800">
      
      {/* Sidebar - Dark */}
      <aside className="w-16 lg:w-56 bg-dhruva-nav text-slate-300 flex flex-col shadow-xl z-20">
        <div className="h-16 flex items-center justify-center lg:justify-start lg:px-4 border-b border-slate-700/50">
          <Ship className="w-8 h-8 text-blue-400 shrink-0" />
          <span className="hidden lg:block ml-3 font-bold text-xl text-white tracking-wide">DHRUVA</span>
        </div>
        <nav className="flex-1 py-4 flex flex-col gap-2">
          <NavItem icon={<Ship />} label="Fleet" active />
          <NavItem icon={<MapIcon />} label="Map" />
          <NavItem icon={<Radio />} label="Advisories" />
          <NavItem icon={<BarChart2 />} label="Analytics" />
          <NavItem icon={<Settings />} label="Settings" />
        </nav>
      </aside>

      {/* Fleet Panel */}
      <div className="w-80 bg-white border-r border-gray-200 flex flex-col z-10 shadow-sm">
        <div className="p-4 border-b border-gray-100 flex justify-between items-center">
          <h2 className="font-bold text-lg">Fleet (12)</h2>
          <Maximize className="w-4 h-4 text-gray-400" />
        </div>
        <div className="p-4 border-b border-gray-100 space-y-3">
          <div className="relative">
            <Search className="w-4 h-4 absolute left-3 top-2.5 text-gray-400" />
            <input 
              type="text" 
              placeholder="Search vessel..." 
              className="w-full pl-9 pr-3 py-2 bg-gray-50 border border-gray-200 rounded-md text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
          </div>
          <div className="flex gap-2">
            <FilterPill label="All" active />
            <FilterPill label="Safe" />
            <FilterPill label="Caution" />
            <FilterPill label="No-Go" />
          </div>
        </div>
        <div className="flex-1 overflow-y-auto">
          <FleetItem name="DH-001" lat="13.221° N" lon="80.145° E" time="Updated 12 min ago" status="SAFE" />
          <FleetItem name="DH-002" lat="13.912° N" lon="80.732° E" time="Updated 8 min ago" status="CAUTION" breach />
          <FleetItem name="DH-007" lat="13.805° N" lon="80.955° E" time="Updated 2 hrs ago" status="NO-GO" breach active />
          <FleetItem name="DH-012" lat="13.120° N" lon="80.412° E" time="Updated 15 min ago" status="SAFE" />
          <FleetItem name="DH-015" lat="13.660° N" lon="80.601° E" time="Updated 31 min ago" status="CAUTION" />
          <FleetItem name="DH-018" lat="14.005° N" lon="80.321° E" time="Updated 28 min ago" status="SAFE" />
        </div>
      </div>

      {/* Main Content */}
      <main className="flex-1 flex flex-col min-w-0">
        {/* Top Header */}
        <header className="h-16 bg-white border-b border-gray-200 flex items-center justify-between px-6 shrink-0">
          <div className="flex items-center gap-4">
            <h1 className="font-bold text-lg">Maritime Operating Picture</h1>
            <span className="text-xs text-gray-400">|</span>
            <span className="text-sm text-gray-500">ISRO PS 26176</span>
          </div>
          <div className="flex items-center gap-6">
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 rounded-full bg-green-500"></div>
              <div className="text-xs">
                <p className="font-semibold text-gray-700 leading-tight">System Online</p>
                <p className="text-gray-400">Last Sync: 12 min ago</p>
              </div>
            </div>
            <div className="flex items-center gap-2 bg-gray-50 border border-gray-200 px-3 py-1.5 rounded-md text-sm">
              <Calendar className="w-4 h-4 text-gray-500" />
              <span>Last 24 Hours</span>
            </div>
          </div>
        </header>

        {/* Map Area */}
        <div className="flex-1 bg-slate-200 relative p-4 pb-0 flex flex-col min-h-0">
          <div className="flex-1 rounded-t-xl border-t border-l border-r border-gray-300 relative overflow-hidden flex flex-col shadow-inner bg-slate-800">
            
            <MapProvider>
              <ReactMapGL
                initialViewState={{
                  longitude: 80.5,
                  latitude: 13.5,
                  zoom: 6
                }}
                mapStyle="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json"
                style={{ width: '100%', height: '100%' }}
                attributionControl={false}
              >
                {/* Map Controls (Overlay) */}
                <div className="absolute top-4 left-4 flex gap-2 z-10">
                  <LayerBtn label="SST" active />
                  <LayerBtn label="Chlorophyll" />
                  <LayerBtn label="Wave Height" />
                  <LayerBtn label="PFZ" />
                  <LayerBtn label="IMBL/MPA" />
                </div>
                <div className="absolute top-4 right-4 flex flex-col gap-2 z-10">
                  <button className="bg-white p-2 rounded shadow text-gray-700 hover:text-black"><Maximize className="w-5 h-5" /></button>
                  <div className="bg-white rounded shadow flex flex-col text-gray-700">
                    <button className="p-2 border-b border-gray-100 hover:text-black"><Plus className="w-5 h-5" /></button>
                    <button className="p-2 hover:text-black"><Minus className="w-5 h-5" /></button>
                  </div>
                  <button className="bg-white p-2 rounded shadow text-gray-700 hover:text-black"><Layers className="w-5 h-5" /></button>
                </div>

                {/* Boat Marker (DH-007) */}
                <Marker longitude={80.955} latitude={13.805} anchor="bottom">
                  <div className="flex flex-col items-center">
                    <div className="bg-danger text-white p-1.5 rounded-sm shadow-lg mb-1 relative">
                      <Ship className="w-4 h-4" />
                      <div className="absolute -bottom-1 left-1/2 -translate-x-1/2 border-l-4 border-r-4 border-t-4 border-l-transparent border-r-transparent border-t-danger"></div>
                    </div>
                    <span className="bg-black/75 text-white text-[10px] px-1.5 py-0.5 rounded shadow">DH-007</span>
                  </div>
                </Marker>

                <div className="absolute bottom-4 right-4 bg-black/75 text-white text-xs px-3 py-1.5 rounded shadow z-10">
                  Lat: 13.805° N &nbsp;|&nbsp; Lon: 80.955° E
                </div>
              </ReactMapGL>
            </MapProvider>
          </div>
        </div>

        {/* Bottom Dashboard Area */}
        <div className="h-64 bg-gray-50 border-t border-gray-200 p-4 shrink-0 flex flex-col gap-4 overflow-y-auto">
          {/* Quick Stats */}
          <div className="flex gap-4">
            <StatCard icon={<Thermometer className="w-4 h-4 text-blue-500" />} label="Sea Surface Temp (SST)" value="28.4" unit="°C" trend="+0.6" />
            <StatCard icon={<Leaf className="w-4 h-4 text-green-600" />} label="Chlorophyll" value="0.42" unit="mg/m³" trend="+12%" />
            <StatCard icon={<Waves className="w-4 h-4 text-blue-500" />} label="Wave Height" value="2.4" unit="m" trend="+0.3" />
            <StatCard icon={<Target className="w-4 h-4 text-blue-600" />} label="Active PFZ Zones" value="14" unit="" trend="+2" />
            <StatCard icon={<Ship className="w-4 h-4 text-indigo-600" />} label="Vessels Tracked" value="12" unit="" status="Online" />
          </div>

          {/* Broadcast Composer */}
          <div className="bg-white rounded-lg border border-gray-200 p-4 flex gap-6">
            <div className="flex-1">
              <div className="flex items-center gap-2 mb-2">
                <Radio className="w-5 h-5 text-gray-700" />
                <h3 className="font-bold">Broadcast Composer</h3>
              </div>
              <textarea 
                className="w-full h-20 p-3 bg-gray-50 border border-gray-200 rounded-md text-sm text-gray-700 resize-none focus:outline-none focus:ring-1 focus:ring-blue-500"
                defaultValue="NO-GO: Unsafe wave and wind conditions detected in your area. Maintain safe distance from the International Maritime Boundary Line. Await further advisory. — Dhruva (ISRO)"
              />
              <div className="flex gap-3 mt-3">
                <button className="text-sm text-gray-600 border border-gray-200 px-3 py-1.5 rounded flex items-center gap-1 hover:bg-gray-50">
                  Generate from Template
                </button>
                <button className="text-sm text-gray-600 border border-gray-200 px-3 py-1.5 rounded flex items-center gap-1 hover:bg-gray-50">
                  Clear
                </button>
              </div>
            </div>
            
            <div className="w-80 flex flex-col">
              <div className="flex justify-end mb-4">
                <select className="text-sm border border-gray-200 rounded-md px-3 py-1.5 bg-gray-50">
                  <option>DH-007 — Matsya Seven</option>
                </select>
              </div>
              
              <div className="bg-gray-50 rounded-md p-3 mb-auto border border-gray-100">
                <div className="flex justify-between items-center mb-1">
                  <span className="text-xs font-semibold text-gray-500 uppercase">Payload Cost</span>
                  <Info className="w-3 h-3 text-gray-400" />
                </div>
                <div className="flex justify-between items-baseline mb-2">
                  <span className="font-bold text-gray-800"><span className="text-lg">145</span> / 220 bits</span>
                  <span className="text-xs text-gray-500">66%</span>
                </div>
                <div className="w-full bg-gray-200 rounded-full h-1.5 mb-2">
                  <div className="bg-safe h-1.5 rounded-full" style={{ width: '66%' }}></div>
                </div>
                <div className="flex items-center gap-1 text-[10px] font-medium text-safe">
                  <CheckCircle2 className="w-3 h-3" />
                  <span>Fits in single satellite ping</span>
                </div>
              </div>
              
              <button className="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-2.5 rounded-md flex items-center justify-center gap-2 mt-3 transition-colors">
                <Send className="w-4 h-4" />
                Broadcast Advisory
              </button>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}

function NavItem({ icon, label, active }: { icon: React.ReactNode, label: string, active?: boolean }) {
  return (
    <div className={`flex items-center lg:px-4 py-3 mx-2 rounded-lg cursor-pointer transition-colors ${active ? 'bg-blue-600 text-white' : 'hover:bg-slate-800 text-slate-400'}`}>
      <div className="w-6 h-6 flex justify-center items-center">{icon}</div>
      <span className="hidden lg:block ml-3 font-medium text-sm">{label}</span>
    </div>
  );
}

function FilterPill({ label, active }: { label: string, active?: boolean }) {
  return (
    <button className={`px-3 py-1 rounded-full text-xs font-medium ${
      active ? 'bg-blue-600 text-white' : 'bg-white border border-gray-200 text-gray-600 hover:bg-gray-50'
    }`}>
      {label}
    </button>
  );
}

function FleetItem({ name, lat, lon, time, status, breach, active }: { name: string, lat: string, lon: string, time: string, status: string, breach?: boolean, active?: boolean }) {
  const statusColor = status === 'SAFE' ? 'bg-safe text-white' : status === 'CAUTION' ? 'bg-caution text-white' : 'bg-danger text-white';
  return (
    <div className={`p-4 border-b border-gray-100 cursor-pointer flex gap-3 items-start relative ${active ? 'bg-blue-50/50' : 'hover:bg-gray-50'}`}>
      {active && <div className="absolute left-0 top-0 bottom-0 w-1 bg-blue-500"></div>}
      <div className="mt-1"><Ship className="w-5 h-5 text-gray-400" /></div>
      <div className="flex-1 min-w-0">
        <div className="flex justify-between items-start mb-1">
          <h4 className="font-bold text-gray-800 truncate">{name}</h4>
          <span className={`text-[10px] px-2 py-0.5 rounded font-bold tracking-wider ${statusColor}`}>{status}</span>
        </div>
        <p className="text-xs text-gray-500 truncate mb-1">{lat}, {lon}</p>
        <p className="text-[10px] text-gray-400">{time}</p>
        {breach && (
          <div className="flex items-center gap-1 text-danger mt-1">
            <AlertTriangle className="w-3 h-3" />
            <span className="text-[10px] font-bold">Breach Watch</span>
          </div>
        )}
      </div>
      <ChevronRight className="w-4 h-4 text-gray-300 mt-2 shrink-0" />
    </div>
  );
}

function LayerBtn({ label, active }: { label: string, active?: boolean }) {
  return (
    <button className={`px-3 py-1.5 rounded shadow text-xs font-medium backdrop-blur-sm ${
      active ? 'bg-blue-600 text-white' : 'bg-slate-900/70 text-white hover:bg-slate-900/90'
    }`}>
      {label}
    </button>
  );
}

function StatCard({ icon, label, value, unit, trend, status }: any) {
  return (
    <div className="flex-1 bg-white border border-gray-200 rounded-lg p-3 flex flex-col">
      <div className="flex items-center gap-1.5 mb-2">
        {icon}
        <span className="text-xs font-medium text-gray-600 truncate">{label}</span>
      </div>
      <div className="mt-auto flex items-end justify-between">
        <div className="flex items-baseline gap-1">
          <span className="text-2xl font-bold text-gray-900 leading-none">{value}</span>
          <span className="text-xs font-medium text-gray-500">{unit}</span>
        </div>
        {trend && <span className="text-xs font-semibold text-green-600">{trend}</span>}
        {status && <span className="text-xs font-semibold text-safe">{status}</span>}
      </div>
    </div>
  );
}
