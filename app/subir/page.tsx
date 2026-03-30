import UploadForm from '@/components/UploadForm';
import { getDb } from '@/lib/db';
import type { Servicio } from '@/lib/types';

interface Props {
  searchParams: Promise<{ anio?: string; mes?: string }>;
}

export default async function SubirPage({ searchParams }: Props) {
  const sp = await searchParams;
  const db = getDb();
  const servicios = db.prepare('SELECT * FROM servicios ORDER BY nombre').all() as Servicio[];

  const now = new Date();
  const defaultAnio = sp.anio ? Number(sp.anio) : now.getFullYear();
  const defaultMes = sp.mes ? Number(sp.mes) : now.getMonth() + 1;

  return (
    <div className="max-w-lg mx-auto space-y-6">
      <h1 className="text-2xl font-bold">Subir documento</h1>
      {servicios.length === 0 ? (
        <p className="text-gray-500">
          No hay servicios configurados.{' '}
          <a href="/servicios" className="text-blue-600 hover:underline">
            Agregar servicios
          </a>
        </p>
      ) : (
        <UploadForm
          servicios={servicios}
          defaultAnio={defaultAnio}
          defaultMes={defaultMes}
        />
      )}
    </div>
  );
}
