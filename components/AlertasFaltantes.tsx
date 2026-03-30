import type { EstadoServicio } from '@/lib/types';

interface Props {
  faltantes: EstadoServicio[];
}

export default function AlertasFaltantes({ faltantes }: Props) {
  if (faltantes.length === 0) return null;

  const nombres = faltantes.map(f => f.servicio.nombre).join(', ');

  return (
    <div className="bg-yellow-100 border border-yellow-400 text-yellow-800 px-4 py-3 rounded">
      <strong>Atencion:</strong> Faltan comprobantes de pago para: {nombres}
    </div>
  );
}
