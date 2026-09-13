import { useEffect, useRef, useState } from "react";
import jsQR from "jsqr";
import { decodeCapsule } from "../shared/capsule/decode";
import { renderReason, type Language } from "../shared/capsule/codebook";

export function advisoryFor(payload: string, lang: Language) {
  const capsule = decodeCapsule(payload);
  return renderReason(capsule, lang);
}

export function ScanView({ lang = "ta" }: { lang?: Language }) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [advisory, setAdvisory] = useState<{ text: string; degraded: boolean } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let animationFrameId: number;
    let active = true;
    const videoElem = videoRef.current;

    async function setupCamera() {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } });
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          videoRef.current.setAttribute("playsinline", "true");
          await videoRef.current.play();
          tick();
        }
      } catch (_err) {
        if (active) setError("Could not access camera");
      }
    }

    function tick() {
      if (!active || !videoRef.current || !canvasRef.current) return;
      if (videoRef.current.readyState === videoRef.current.HAVE_ENOUGH_DATA) {
        const canvas = canvasRef.current;
        const video = videoRef.current;
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        const ctx = canvas.getContext("2d");
        if (ctx) {
          ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
          const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
          const code = jsQR(imageData.data, imageData.width, imageData.height, {
            inversionAttempts: "dontInvert",
          });

          if (code) {
            try {
              const res = advisoryFor(code.data, lang);
              setAdvisory(res);
              speak(res.text, lang, res);
              // Stop camera after successful scan
              if (video.srcObject) {
                (video.srcObject as MediaStream).getTracks().forEach((track) => track.stop());
              }
              return;
            } catch (_e) {
              // Ignore invalid QRs and keep scanning
            }
          }
        }
      }
      animationFrameId = requestAnimationFrame(tick);
    }

    setupCamera();

    return () => {
      active = false;
      if (animationFrameId) cancelAnimationFrame(animationFrameId);
      if (videoElem && videoElem.srcObject) {
        (videoElem.srcObject as MediaStream).getTracks().forEach((track) => track.stop());
      }
    };
  }, [lang]);

  // Offline speech path (Step 4)
  function speak(text: string, language: string, res?: { degraded: boolean }) {
    if ("speechSynthesis" in window) {
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.lang = language;
      window.speechSynthesis.speak(utterance);
    } else {
      // Fallback to pre-rendered audio if TTS is unavailable
      // E.g., caching service worker returns the clip for this entry
      // For now, we simulate this fallback path.
      console.log("Fallback to pre-rendered audio for: ", text);
    }
  }

  return (
    <div style={{ padding: "20px" }}>
      <h2>Scan Capsule QR</h2>
      {error && <div style={{ color: "red" }}>{error}</div>}
      {!advisory && (
        <div style={{ position: "relative" }}>
          <video ref={videoRef} style={{ width: "100%", maxWidth: "400px" }} />
          <canvas ref={canvasRef} style={{ display: "none" }} />
        </div>
      )}
      {advisory && (
        <div style={{ marginTop: "20px", padding: "10px", border: "1px solid #ccc" }}>
          <h3>Advisory ({lang})</h3>
          {advisory.degraded && (
            <div style={{ color: "orange", marginBottom: "10px" }}>
              <strong>Warning:</strong> Degraded advisory.
            </div>
          )}
          <p>{advisory.text}</p>
          <button onClick={() => speak(advisory.text, lang)}>Replay Audio</button>
        </div>
      )}
    </div>
  );
}
