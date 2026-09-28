import { useEffect, useRef, useState } from "react";
import jsQR from "jsqr";

/** Camera QR reader. `accept` returns true to stop on a code, false to keep
 * looking (a QR that is not what this screen expects is ignored). */
export function QrCamera({ accept, hint }: { accept: (text: string) => boolean; hint: string }) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const acceptRef = useRef(accept);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    acceptRef.current = accept;
  }, [accept]);

  useEffect(() => {
    let frame = 0;
    let active = true;
    let stream: MediaStream | null = null;

    const tick = () => {
      const video = videoRef.current;
      const canvas = canvasRef.current;
      if (!active || !video || !canvas) return;
      if (video.readyState === video.HAVE_ENOUGH_DATA) {
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        const ctx = canvas.getContext("2d", { willReadFrequently: true });
        if (ctx) {
          ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
          const img = ctx.getImageData(0, 0, canvas.width, canvas.height);
          const code = jsQR(img.data, img.width, img.height, { inversionAttempts: "dontInvert" });
          if (code && acceptRef.current(code.data)) {
            active = false;
            stream?.getTracks().forEach((t) => t.stop());
            return;
          }
        }
      }
      frame = requestAnimationFrame(tick);
    };

    navigator.mediaDevices
      .getUserMedia({ video: { facingMode: "environment" } })
      .then(async (s) => {
        stream = s;
        if (!active || !videoRef.current) return s.getTracks().forEach((t) => t.stop());
        videoRef.current.srcObject = s;
        videoRef.current.setAttribute("playsinline", "true");
        await videoRef.current.play();
        tick();
      })
      .catch(() => active && setError("The camera is not available. Allow camera access and try again."));

    return () => {
      active = false;
      cancelAnimationFrame(frame);
      stream?.getTracks().forEach((t) => t.stop());
    };
  }, []);

  if (error) return <p className="p-4 text-base font-semibold text-white bg-danger rounded-xl">{error}</p>;
  return (
    <div className="relative w-full h-full">
      <video ref={videoRef} className="absolute inset-0 w-full h-full object-cover" muted />
      <canvas ref={canvasRef} className="hidden" />
      <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
        <div className="w-60 h-60 rounded-2xl border-4 border-white/90 shadow-[0_0_0_2000px_rgb(15_42_54/0.45)]" />
        <p className="mt-5 text-white text-lg font-semibold bg-ink/70 px-4 py-2 rounded-xl">{hint}</p>
      </div>
    </div>
  );
}
