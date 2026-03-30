import { NextRequest, NextResponse } from 'next/server';
import { getDb } from '@/lib/db';
import fs from 'fs';
import path from 'path';

const MIME_TYPES: Record<string, string> = {
  '.pdf': 'application/pdf',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.webp': 'image/webp',
};

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  const db = getDb();
  const doc = db.prepare('SELECT nombre_archivo, ruta_archivo FROM documentos WHERE id = ?')
    .get(Number(id)) as { nombre_archivo: string; ruta_archivo: string } | undefined;

  if (!doc) {
    return NextResponse.json({ error: 'No encontrado' }, { status: 404 });
  }

  if (!fs.existsSync(doc.ruta_archivo)) {
    return NextResponse.json({ error: 'Archivo no encontrado en disco' }, { status: 404 });
  }

  const buffer = fs.readFileSync(doc.ruta_archivo);
  const ext = path.extname(doc.nombre_archivo).toLowerCase();
  const contentType = MIME_TYPES[ext] || 'application/octet-stream';

  return new NextResponse(buffer, {
    headers: {
      'Content-Type': contentType,
      'Content-Disposition': `inline; filename="${doc.nombre_archivo}"`,
    },
  });
}
