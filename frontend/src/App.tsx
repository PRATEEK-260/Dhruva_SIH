import { BrowserRouter, Routes, Route, Link } from "react-router-dom";
import { Radio, Smartphone, Map } from "lucide-react";
import { BoatApp } from "./boat/BoatApp";
import { ShoreApp } from "./shore/ShoreApp";
import { EmulatorApp } from "./emulator/EmulatorApp";

const SCREENS = [
  {
    to: "/boat",
    icon: Smartphone,
    title: "Fisherman's phone",
    body: "Ask by voice in your language. See the verdict, the numbers behind it, and the way home.",
  },
  {
    to: "/emulator",
    icon: Radio,
    title: "Boat terminal",
    body: "Stands in for the DAT-SG box on the boat: sends a question up as one byte, brings a 145-bit answer down.",
  },
  {
    to: "/shore",
    icon: Map,
    title: "Shore console",
    body: "Boundaries, fishing zones and satellite layers on the map, and the log of advisories sent.",
  },
];

function Home() {
  return (
    <div className="min-h-dvh bg-ink text-white px-6 py-12">
      <div className="max-w-3xl mx-auto">
        <p className="text-5xl font-extrabold tracking-wide">DHRUVA</p>
        <h1 className="text-2xl sm:text-3xl font-semibold mt-4 leading-snug max-w-2xl">
          A fisherman asks in his own language and gets an answer for his boat. Out of mobile range,
          the same answer still arrives, in one satellite message.
        </h1>
        <ul className="mt-10 grid gap-4">
          {SCREENS.map((s) => (
            <li key={s.to}>
              <Link
                to={s.to}
                className="flex gap-5 items-start rounded-2xl bg-white text-ink p-5 hover:bg-mist transition-colors"
              >
                <s.icon className="w-9 h-9 text-sea shrink-0 mt-1" />
                <span>
                  <span className="block text-xl font-extrabold">{s.title}</span>
                  <span className="block text-base text-ink-soft mt-1 leading-snug">{s.body}</span>
                </span>
              </Link>
            </li>
          ))}
        </ul>
        <p className="text-white/60 mt-10 text-sm leading-relaxed">
          ISRO problem statement 26176. Advisory only: follow official INCOIS and IMD warnings.
          Satellite and Bluetooth links are simulated; boundaries are indicative, not legal.
        </p>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/boat" element={<BoatApp />} />
        <Route path="/shore" element={<ShoreApp />} />
        <Route path="/emulator" element={<EmulatorApp />} />
        <Route path="/" element={<Home />} />
      </Routes>
    </BrowserRouter>
  );
}
