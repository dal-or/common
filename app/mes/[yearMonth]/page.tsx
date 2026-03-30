import { getDb } from '@/lib/db';
import { nombreMes } from '@/lib/mail';
import type { Documento, Servicio, EstadoServicio } from '@/lib/types';
import MonthSelector from '@/components/MonthSelector';
import ServiceStatusTable from '@/components/ServiceStatusTable';
import AlertasFaltantes from '@/components/AlertasFaltantes';
import EnviarCorreoButton from '@/components/EnviarCorreoButton';
import Link from 'next/link';

interface Props {
  params: Promise<{ yearMonth: string }>;
}

export default async function MesPage({ params }: Props) {
  const { yearMonth } = await params;
  const [anioStr, mesStr] = yearMonth.split('-');
  const anio = Number(anioStr);
  const mes = Number(mesStr);

  if (!anio || !mes || mes < 1 || mes > 12) {
    return <div className="text-red-600">Formato invalido. Usar: /mes/2026-03</div>;
  }

  const db = getDb();
  const servicios = db.prepare('SELECT * FROM servicios ORDER BY nombre').all() as Servicio[];
  const documentos = db.prepare(
    'SELECT * FROM documentos WHERE anio = ? AND mes = ?'
  ).all(anio, mes) as Documento[];

  const estados: EstadoServicio[] = servicios.map(servicio => ({
    servicio,
    factura: documentos.find(d => d.servicio_id === servicio.id && d.tipo === 'factura') || null,
    comprobante: documentos.find(d => d.servicio_id === servicio.id && d.tipo === 'comprobante') || null,
  }));

  const faltantes = estados.filter(e => e.factura && !e.comprobante);
  const totalDocs = documentos.length;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-4">
        <h1 className="text-2xl font-bold">
          {nombreMes(mes)} {anio}
        </h1>
        <MonthSelector current={yearMonth} />
      </div>

      <AlertasFaltantes faltantes={faltantes} />

      <ServiceStatusTable estados={estados} anio={anio} mes={mes} />

      <div className="flex gap-3 flex-wrap">
        <Link
          href={`/subir?anio=${anio}&mes=${mes}`}
          className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700 text-sm"
        >
          Subir documento
        </Link>
        {totalDocs > 0 && (
          <EnviarCorreoButton anio={anio} mes={mes} totalDocs={totalDocs} />
        )}
      </div>
    </div>
  );
}
