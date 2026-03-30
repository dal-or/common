import { NextRequest, NextResponse } from 'next/server';
import { getDb } from '@/lib/db';

export async function GET() {
  const db = getDb();
  const servicios = db.prepare('SELECT * FROM servicios ORDER BY nombre').all();
  return NextResponse.json(servicios);
}

export async function POST(request: NextRequest) {
  const { nombre } = await request.json();

  if (!nombre || typeof nombre !== 'string' || nombre.trim().length === 0) {
    return NextResponse.json({ error: 'Se requiere un nombre' }, { status: 400 });
  }

  const db = getDb();
  try {
    const result = db.prepare('INSERT INTO servicios (nombre) VALUES (?)').run(nombre.trim());
    return NextResponse.json({ id: result.lastInsertRowid, nombre: nombre.trim() }, { status: 201 });
  } catch {
    return NextResponse.json({ error: 'El servicio ya existe' }, { status: 409 });
  }
}

export async function DELETE(request: NextRequest) {
  const { searchParams } = request.nextUrl;
  const id = searchParams.get('id');

  if (!id) {
    return NextResponse.json({ error: 'Se requiere id' }, { status: 400 });
  }

  const db = getDb();
  const docs = db.prepare('SELECT COUNT(*) as count FROM documentos WHERE servicio_id = ?').get(Number(id)) as { count: number };

  if (docs.count > 0) {
    return NextResponse.json(
      { error: 'No se puede eliminar un servicio que tiene documentos asociados' },
      { status: 409 }
    );
  }

  db.prepare('DELETE FROM servicios WHERE id = ?').run(Number(id));
  return NextResponse.json({ ok: true });
}
