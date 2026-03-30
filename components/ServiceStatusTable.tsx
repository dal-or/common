'use client';

import type { EstadoServicio } from '@/lib/types';
import { useRouter } from 'next/navigation';

interface Props {
  estados: EstadoServicio[];
  anio: number;
  mes: number;
}

export default function ServiceStatusTable({ estados, anio, mes }: Props) {
  const router = useRouter();

  async function handleDelete(docId: number) {
    if (!confirm('Eliminar este documento?')) return;
    await fetch(`/api/documentos?id=${docId}`, { method: 'DELETE' });
    router.refresh();
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="bg-gray-100 text-left">
            <th className="p-3 border">Servicio</th>
            <th className="p-3 border">Factura</th>
            <th className="p-3 border">Comprobante</th>
            <th className="p-3 border">Estado</th>
          </tr>
        </thead>
        <tbody>
          {estados.map(({ servicio, factura, comprobante }) => {
            let estado: string;
            let rowClass: string;

            if (factura && comprobante) {
              estado = 'Completo';
              rowClass = 'bg-green-50';
            } else if (factura && !comprobante) {
              estado = 'Falta comprobante';
              rowClass = 'bg-yellow-50';
            } else if (!factura && comprobante) {
              estado = 'Falta factura';
              rowClass = 'bg-yellow-50';
            } else {
              estado = 'Sin documentos';
              rowClass = '';
            }

            return (
              <tr key={servicio.id} className={rowClass}>
                <td className="p-3 border font-medium">{servicio.nombre}</td>
                <td className="p-3 border">
                  {factura ? (
                    <div className="flex items-center gap-2">
                      <a
                        href={`/api/archivos/${factura.id}`}
                        target="_blank"
                        className="text-blue-600 hover:underline"
                      >
                        {factura.nombre_archivo}
                      </a>
                      {factura.monto && (
                        <span className="text-gray-500">(${factura.monto})</span>
                      )}
                      <button
                        onClick={() => handleDelete(factura.id)}
                        className="text-red-400 hover:text-red-600 text-xs"
                        title="Eliminar"
                      >
                        x
                      </button>
                    </div>
                  ) : (
                    <span className="text-gray-400">-</span>
                  )}
                </td>
                <td className="p-3 border">
                  {comprobante ? (
                    <div className="flex items-center gap-2">
                      <a
                        href={`/api/archivos/${comprobante.id}`}
                        target="_blank"
                        className="text-blue-600 hover:underline"
                      >
                        {comprobante.nombre_archivo}
                      </a>
                      <button
                        onClick={() => handleDelete(comprobante.id)}
                        className="text-red-400 hover:text-red-600 text-xs"
                        title="Eliminar"
                      >
                        x
                      </button>
                    </div>
                  ) : (
                    <span className="text-gray-400">-</span>
                  )}
                </td>
                <td className="p-3 border">
                  <span
                    className={
                      estado === 'Completo'
                        ? 'text-green-700 font-medium'
                        : estado === 'Sin documentos'
                        ? 'text-gray-400'
                        : 'text-yellow-700 font-medium'
                    }
                  >
                    {estado}
                  </span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      {estados.length === 0 && (
        <p className="text-gray-500 text-center py-4">
          No hay servicios configurados.{' '}
          <a href="/servicios" className="text-blue-600 hover:underline">
            Agregar servicios
          </a>
        </p>
      )}
    </div>
  );
}
