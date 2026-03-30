import ServiciosManager from '@/components/ServiciosManager';
import { getDb } from '@/lib/db';
import type { Servicio } from '@/lib/types';

export default async function ServiciosPage() {
  const db = getDb();
  const servicios = db.prepare('SELECT * FROM servicios ORDER BY nombre').all() as Servicio[];

  return (
    <div className="max-w-lg mx-auto space-y-6">
      <h1 className="text-2xl font-bold">Servicios</h1>
      <p className="text-gray-600 text-sm">
        Configura los servicios que pagas mensualmente. Los servicios por defecto son:
        Electricidad, Gas, Agua, Internet, Administracion.
      </p>
      <ServiciosManager initialServicios={servicios} />
    </div>
  );
}
