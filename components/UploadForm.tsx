'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import type { Servicio, TipoDocumento } from '@/lib/types';

interface Props {
  servicios: Servicio[];
  defaultAnio: number;
  defaultMes: number;
}

export default function UploadForm({ servicios, defaultAnio, defaultMes }: Props) {
  const router = useRouter();
  const [servicioId, setServicioId] = useState(String(servicios[0]?.id || ''));
  const [anio, setAnio] = useState(defaultAnio);
  const [mes, setMes] = useState(defaultMes);
  const [tipo, setTipo] = useState<TipoDocumento>('factura');
  const [monto, setMonto] = useState('');
  const [archivo, setArchivo] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!archivo) {
      setError('Selecciona un archivo');
      return;
    }

    setUploading(true);
    setError('');

    const formData = new FormData();
    formData.append('servicio_id', servicioId);
    formData.append('anio', String(anio));
    formData.append('mes', String(mes));
    formData.append('tipo', tipo);
    formData.append('archivo', archivo);
    if (monto) formData.append('monto', monto);

    try {
      const res = await fetch('/api/documentos', { method: 'POST', body: formData });
      const data = await res.json();

      if (!res.ok) {
        setError(data.error || 'Error al subir');
        return;
      }

      const ym = `${anio}-${String(mes).padStart(2, '0')}`;
      router.push(`/mes/${ym}`);
      router.refresh();
    } catch {
      setError('Error de conexion');
    } finally {
      setUploading(false);
    }
  }

  const meses = [
    'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
    'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre',
  ];

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label className="block text-sm font-medium mb-1">Servicio</label>
        <select
          value={servicioId}
          onChange={e => setServicioId(e.target.value)}
          className="w-full border rounded p-2"
        >
          {servicios.map(s => (
            <option key={s.id} value={s.id}>{s.nombre}</option>
          ))}
        </select>
      </div>

      <div className="flex gap-4">
        <div className="flex-1">
          <label className="block text-sm font-medium mb-1">Mes</label>
          <select
            value={mes}
            onChange={e => setMes(Number(e.target.value))}
            className="w-full border rounded p-2"
          >
            {meses.map((nombre, i) => (
              <option key={i + 1} value={i + 1}>{nombre}</option>
            ))}
          </select>
        </div>
        <div className="w-28">
          <label className="block text-sm font-medium mb-1">Anio</label>
          <input
            type="number"
            value={anio}
            onChange={e => setAnio(Number(e.target.value))}
            className="w-full border rounded p-2"
            min={2020}
            max={2100}
          />
        </div>
      </div>

      <div>
        <label className="block text-sm font-medium mb-1">Tipo de documento</label>
        <div className="flex gap-4">
          <label className="flex items-center gap-2">
            <input
              type="radio"
              name="tipo"
              value="factura"
              checked={tipo === 'factura'}
              onChange={() => setTipo('factura')}
            />
            Factura
          </label>
          <label className="flex items-center gap-2">
            <input
              type="radio"
              name="tipo"
              value="comprobante"
              checked={tipo === 'comprobante'}
              onChange={() => setTipo('comprobante')}
            />
            Comprobante de pago
          </label>
        </div>
      </div>

      <div>
        <label className="block text-sm font-medium mb-1">Monto (opcional)</label>
        <input
          type="number"
          step="0.01"
          value={monto}
          onChange={e => setMonto(e.target.value)}
          className="w-full border rounded p-2"
          placeholder="Ej: 5430.50"
        />
      </div>

      <div>
        <label className="block text-sm font-medium mb-1">Archivo</label>
        <input
          type="file"
          accept=".pdf,.png,.jpg,.jpeg,.webp"
          onChange={e => setArchivo(e.target.files?.[0] || null)}
          className="w-full border rounded p-2"
        />
      </div>

      {error && <p className="text-red-600 text-sm">{error}</p>}

      <button
        type="submit"
        disabled={uploading}
        className="bg-blue-600 text-white px-6 py-2 rounded hover:bg-blue-700 disabled:opacity-50"
      >
        {uploading ? 'Subiendo...' : 'Subir'}
      </button>
    </form>
  );
}
