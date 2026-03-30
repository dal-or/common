'use client';

import { useState } from 'react';

interface Props {
  anio: number;
  mes: number;
  totalDocs: number;
}

export default function EnviarCorreoButton({ anio, mes, totalDocs }: Props) {
  const [sending, setSending] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; message: string } | null>(null);

  async function handleSend() {
    const ok = confirm(
      `Se enviara un correo con ${totalDocs} documento(s) adjuntos. Continuar?`
    );
    if (!ok) return;

    setSending(true);
    setResult(null);

    try {
      const res = await fetch('/api/enviar-correo', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ anio, mes }),
      });
      const data = await res.json();

      if (res.ok) {
        setResult({ ok: true, message: `Correo enviado con ${data.enviados} adjunto(s)` });
      } else {
        setResult({ ok: false, message: data.error || 'Error desconocido' });
      }
    } catch (err) {
      setResult({ ok: false, message: 'Error de conexion' });
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="flex items-center gap-3">
      <button
        onClick={handleSend}
        disabled={sending}
        className="bg-green-600 text-white px-4 py-2 rounded hover:bg-green-700 disabled:opacity-50 text-sm"
      >
        {sending ? 'Enviando...' : 'Enviar por correo'}
      </button>
      {result && (
        <span className={result.ok ? 'text-green-700 text-sm' : 'text-red-600 text-sm'}>
          {result.message}
        </span>
      )}
    </div>
  );
}
