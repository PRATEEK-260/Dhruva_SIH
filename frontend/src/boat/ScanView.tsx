import { useCallback } from "react";
import { X } from "lucide-react";
import { decodeCapsule, type Capsule } from "../shared/capsule/decode";
import { renderReason, type Language } from "../shared/capsule/codebook";
import { QrCamera } from "../shared/QrCamera";

export function advisoryFor(payload: string, lang: Language) {
  const capsule = decodeCapsule(payload);
  return renderReason(capsule, lang);
}

/** Receive a capsule from the boat terminal. The terminal hands it to the phone
 * over Bluetooth; this demo shows it as a QR on the terminal's screen instead. */
export function ScanView({
  lang = "ta",
  onScan,
  onClose,
}: {
  lang?: Language;
  onScan: (res: { payload: string; advisory: { text: string; degraded: boolean }; capsule: Capsule }) => void;
  onClose: () => void;
}) {
  const accept = useCallback(
    (text: string) => {
      try {
        const capsule = decodeCapsule(text);
        onScan({ payload: text, advisory: renderReason(capsule, lang), capsule });
        return true;
      } catch {
        return false; // not a capsule; keep looking
      }
    },
    [lang, onScan],
  );

  return (
    <div className="fixed inset-0 bg-ink z-50">
      <QrCamera accept={accept} hint="Point at the boat terminal's screen" />
      <button
        onClick={onClose}
        aria-label="Close"
        className="absolute top-4 right-4 w-14 h-14 rounded-full bg-white text-ink flex items-center justify-center"
      >
        <X className="w-7 h-7" />
      </button>
    </div>
  );
}
