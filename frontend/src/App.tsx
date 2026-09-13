import { useState } from 'react'
import './App.css'
import { ScanView } from './boat/ScanView'
import { type Language, LANGUAGES } from './shared/capsule/codebook'

function App() {
  const [lang, setLang] = useState<Language>("ta");

  return (
    <div style={{ maxWidth: "600px", margin: "0 auto", padding: "20px" }}>
      <h1>Dhruva Boat PWA</h1>
      <div style={{ marginBottom: "20px" }}>
        <label>
          <strong>Select Language: </strong>
          <select value={lang} onChange={(e) => setLang(e.target.value as Language)}>
            {LANGUAGES.map((l) => (
              <option key={l} value={l}>{l.toUpperCase()}</option>
            ))}
          </select>
        </label>
      </div>
      <ScanView lang={lang} />
    </div>
  )
}

export default App
