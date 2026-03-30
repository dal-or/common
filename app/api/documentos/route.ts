import { NextRequest, NextResponse } from 'next/server';
import { getDb } from '@/lib/db';
import path from 'path';
import fs from 'fs';

const UPLOAD_DIR = path.join(process.cwd(), 'uploads');

export async function GET(request: NextRequest) {
  const { searchParams } = request.nextUrl;
  const anio = searchParams.get('anio');
  const mes = searchParams.get('mes');

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
  `).all(Number(anio), Number(mes));

  return NextResponse.json(docs);
}

export async function POST(request: NextRequest) {
  const formData = await request.formData();
  const servicio_id = formData.get('servicio_id') as string;
  const anio = formData.get('anio') as string;
  const mes = formData.get('mes') as string;
  const tipo = formData.get('tipo') as string;
  const monto = formData.get('monto') as string;
  const archivo = formData.get('archivo') as File;

  if (!servicio_id || !anio || !mes || !tipo || !archivo) {
    return NextResponse.json({ error: 'Faltan campos requeridos' }, { status: 400 });
  }

  if (tipo !== 'factura' && tipo !== 'comprobante') {
    return NextResponse.json({ error: 'Tipo debe ser factura o comprobante' }, { status: 400 });
  }

  const subDir = tipo === 'factura' ? 'facturas' : 'comprobantes';
  const uploadPath = path.join(UPLOAD_DIR, subDir);
  fs.mkdirSync(uploadPath, { recursive: true });

  const ext = path.extname(archivo.name) || '.pdf';
  const safeName = `${servicio_id}_${anio}-${mes}_${Date.now()}${ext}`;
  const filePath = path.join(uploadPath, safeName);

  const buffer = Buffer.from(await archivo.arrayBuffer());
  fs.writeFileSync(filePath, buffer);

  const db = getDb();

  // Check if there's already a document for this slot
  const existing = db.prepare(
    'SELECT id, ruta_archivo FROM documentos WHERE servicio_id = ? AND anio = ? AND mes = ? AND tipo = ?'
  ).get(Number(servicio_id), Number(anio), Number(mes), tipo) as { id: number; ruta_archivo: string } | undefined;

  if (existing) {
    // Replace: delete old file and update row
    try { fs.unlinkSync(existing.ruta_archivo); } catch {}
    db.prepare(
      'UPDATE documentos SET nombre_archivo = ?, ruta_archivo = ?, monto = ?, fecha_subida = datetime(\'now\') WHERE id = ?'
    ).run(archivo.name, filePath, monto ? Number(monto) : null, existing.id);

    return NextResponse.json({ id: existing.id, replaced: true });
  }

  const result = db.prepare(`
    INSERT INTO documentos (servicio_id, anio, mes, tipo, nombre_archivo, ruta_archivo, monto)
    VALUES (?, ?, ?, ?, ?, ?, ?)
  `).run(Number(servicio_id), Number(anio), Number(mes), tipo, archivo.name, filePath, monto ? Number(monto) : null);

  return NextResponse.json({ id: result.lastInsertRowid }, { status: 201 });
}

export async function DELETE(request: NextRequest) {
  const { searchParams } = request.nextUrl;
  const id = searchParams.get('id');

  if (!id) {
    return NextResponse.json({ error: 'Se requiere id' }, { status: 400 });
  }

  const db = getDb();
  const doc = db.prepare('SELECT ruta_archivo FROM documentos WHERE id = ?').get(Number(id)) as { ruta_archivo: string } | undefined;

  if (!doc) {
    return NextResponse.json({ error: 'Documento no encontrado' }, { status: 404 });
  }

  try { fs.unlinkSync(doc.ruta_archivo); } catch {}
  db.prepare('DELETE FROM documentos WHERE id = ?').run(Number(id));

  return NextResponse.json({ ok: true });
}
