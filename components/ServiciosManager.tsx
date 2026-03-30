'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import type { Servicio } from '@/lib/types';

interface Props {
  initialServicios: Servicio[];
}

export default function ServiciosManager({ initialServicios }: Props) {
  const router = useRouter();
  const [servicios, setServicios] = useState(initialServicios);
  const [nombre, setNombre] = useState('');
  const [error, setError] = useState('');

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    if (!nombre.trim()) return;

    setError('');
    const res = await fetch('/api/servicios', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ nombre: nombre.trim() }),
    });

    const data = await res.json();
    if (!res.ok) {
      setError(data.error);
      return;
    }

    setServicios([...servicios, data].sort((a, b) => a.nombre.localeCompare(b.nombre)));
    setNombre('');
    router.refresh();
  }

  async function handleDelete(id: number) {
    if (!confirm('Eliminar este servicio?')) return;
    setError('');

    const res = await fetch(`/api/servicios?id=${id}`, { method: 'DELETE' });
    if (!res.ok) {
      const data = await res.json();
      setError(data.error);
      return;
    }

    setServicios(servicios.filter(s => s.id !== id));
    router.refresh();
  }

  return (
    <div className="space-y-4">
      <ul className="divide-y border rounded">
        {servicios.map(s => (
          <li key={s.id} className="flex items-center justify-between p-3">
            <span>{s.nombre}</span>
            <button
              onClick={() => handleDelete(s.id)}
              className="text-red-500 hover:text-red-700 text-sm"
            >
              Eliminar
            </button>
          </li>
        ))}
        {servicios.length === 0 && (
          <li className="p-3 text-gray-400 text-center">No hay servicios</li>
        )}
      </ul>

      <form onSubmit={handleAdd} className="flex gap-2">
        <input
          type="text"
          value={nombre}
          onChange={e => setNombre(e.target.value)}
          placeholder="Nombre del servicio"
          className="flex-1 border rounded p-2"
        />
        <button
          type="submit"
          className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700 text-sm"
        >
          Agregar
        </button>
      </form>

      {error && <p className="text-red-600 text-sm">{error}</p>}
    </div>
  );
}
