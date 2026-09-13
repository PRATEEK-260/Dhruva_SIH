import { useEffect, useRef, useState } from "react";
import jsQR from "jsqr";
import { decodeCapsule } from "../shared/capsule/decode";
import { renderReason, type Language } from "../shared/capsule/codebook";

export function advisoryFor(payload: string, lang: Language) {
  const capsule = decodeCapsule(payload);
  return renderReason(capsule, lang);
}

export function ScanView({ lang = "ta", onScan, onClose }: { lang?: Language, onScan: (res: { payload: string, advisory: { text: string, degraded: boolean }, capsule: any }) => void, onClose: () => void }) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let animationFrameId: number;
    let active = true;
    const videoElem = videoRef.current;

    async function setupCamera() {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } });
        if (videoRef.current && active) {
          videoRef.current.srcObject = stream;
          videoRef.current.setAttribute("playsinline", "true");
          await videoRef.current.play();
          tick();
        }
      } catch (_err) {
        if (active) setError("Could not access camera. Please allow permissions.");
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
              const capsule = decodeCapsule(code.data);
              const advisory = renderReason(capsule, lang);
              
              // Stop camera after successful scan
              if (video.srcObject) {
                (video.srcObject as MediaStream).getTracks().forEach((track) => track.stop());
              }
              active = false;
              onScan({ payload: code.data, advisory, capsule });
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
  }, [lang, onScan]);

  return (
    <div className="fixed inset-0 bg-black z-50 flex flex-col items-center justify-center">
      <div className="absolute top-4 right-4 z-50">
        <button onClick={onClose} className="bg-gray-800 text-white px-4 py-2 rounded-full font-bold">
          Close
        </button>
      </div>
      {error ? (
        <div className="bg-red-500 text-white p-4 rounded m-4">{error}</div>
      ) : (
        <div className="relative w-full h-full flex flex-col items-center justify-center">
          <video ref={videoRef} className="absolute inset-0 w-full h-full object-cover" />
          <canvas ref={canvasRef} style={{ display: "none" }} />
          {/* Overlay Box */}
          <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
            <div className="w-64 h-64 border-4 border-blue-500 rounded-lg box-border relative">
              <div className="absolute -inset-1 border-2 border-transparent bg-gradient-to-b from-blue-500/20 to-transparent mix-blend-overlay"></div>
            </div>
            <p className="mt-4 text-white font-bold bg-black/50 px-4 py-2 rounded">
              Point at QR Code
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

// Offline speech path (Step 4)
export function speak(text: string, language: string, fallbackLog?: () => void) {
  if ("speechSynthesis" in window) {
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = language;
    window.speechSynthesis.speak(utterance);
  } else {
    // Fallback to pre-rendered audio if TTS is unavailable
    if (fallbackLog) fallbackLog();
    console.log("Fallback to pre-rendered audio for: ", text);
  }
}
