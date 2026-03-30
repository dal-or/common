import { NextRequest, NextResponse } from 'next/server';
import { getDb } from '@/lib/db';
import { createTransport, nombreMes } from '@/lib/mail';
import fs from 'fs';
import path from 'path';
import type { Documento } from '@/lib/types';

export async function POST(request: NextRequest) {
  const { anio, mes } = await request.json();

  if (!anio || !mes) {
    return NextResponse.json({ error: 'Se requiere anio y mes' }, { status: 400 });
  }

  const db = getDb();
  const docs = db.prepare(`
    SELECT d.*, s.nombre as servicio_nombre
    FROM documentos d
    JOIN servicios s ON s.id = d.servicio_id
    WHERE d.anio = ? AND d.mes = ?
    ORDER BY s.nombre, d.tipo
  `).all(Number(anio), Number(mes)) as (Documento & { servicio_nombre: string })[];

  if (docs.length === 0) {
    return NextResponse.json({ error: 'No hay documentos para enviar en este periodo' }, { status: 400 });
  }

  // Build attachments
  const attachments = docs
    .filter(d => fs.existsSync(d.ruta_archivo))
    .map(d => ({
      filename: `${d.servicio_nombre}_${d.tipo}${path.extname(d.nombre_archivo)}`,
      path: d.ruta_archivo,
    }));

  // Build email body
  const mesNombre = nombreMes(Number(mes));
  const serviciosIncluidos = [...new Set(docs.map(d => d.servicio_nombre))];
  const detalle = serviciosIncluidos.map(s => {
    const factura = docs.find(d => d.servicio_nombre === s && d.tipo === 'factura');
    const comprobante = docs.find(d => d.servicio_nombre === s && d.tipo === 'comprobante');
    let linea = `  - ${s}: `;
    const partes = [];
    if (factura) partes.push(`factura${factura.monto ? ` ($${factura.monto})` : ''}`);
    if (comprobante) partes.push('comprobante de pago');
    linea += partes.join(' + ');
    return linea;
  }).join('\n');

  const landlordEmail = process.env.LANDLORD_EMAIL;
  const landlordName = process.env.LANDLORD_NAME || 'Propietaria';
  const gmailUser = process.env.GMAIL_USER;

  if (!landlordEmail || !gmailUser) {
    return NextResponse.json(
      { error: 'Configurar GMAIL_USER y LANDLORD_EMAIL en .env.local' },
      { status: 500 }
    );
  }

  const subject = `Comprobantes de servicios - ${mesNombre} ${anio}`;
  const text = `Hola ${landlordName},

Le adjunto las facturas y comprobantes de pago de los servicios correspondientes a ${mesNombre} ${anio}:

${detalle}

Se adjuntan ${attachments.length} archivo(s).

Saludos cordiales`;

  try {
    const transporter = createTransport();
    await transporter.sendMail({
      from: gmailUser,
      to: landlordEmail,
      subject,
      text,
      attachments,
    });

    return NextResponse.json({ ok: true, enviados: attachments.length });
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : 'Error desconocido';
    return NextResponse.json({ error: `Error al enviar: ${message}` }, { status: 500 });
  }
}
