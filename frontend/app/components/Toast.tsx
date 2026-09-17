"use client";
import { useEffect } from "react";
interface ToastProps { message: string; type: "error" | "success" | "info"; onClose: () => void; duration?: number; }
export default function Toast({ message, type, onClose, duration = 6500 }: ToastProps) {
  useEffect(() => {
    if (type === "error") return;
    const timer = setTimeout(onClose, duration);
    return () => clearTimeout(timer);
  }, [duration, onClose, type]);
  return <div className={`qt-toast qt-toast-${type}`} role={type === "error" ? "alert" : "status"}>
    <span className="qt-toast-symbol" aria-hidden="true">{type === "error" ? "!" : type === "success" ? "✓" : "i"}</span>
    <span>{message}</span><button type="button" onClick={onClose} aria-label="关闭提示">×</button>
  </div>;
}

