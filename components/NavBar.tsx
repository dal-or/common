'use client';

import Link from 'next/link';

export default function NavBar() {
  const now = new Date();
  const currentMonth = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;

  return (
    <nav className="bg-white border-b border-gray-200 px-4 py-3">
      <div className="max-w-4xl mx-auto flex items-center justify-between">
        <Link href={`/mes/${currentMonth}`} className="text-lg font-bold text-gray-800">
          Control de Servicios
        </Link>
        <div className="flex gap-4 text-sm">
          <Link href={`/mes/${currentMonth}`} className="text-blue-600 hover:underline">
            Mes actual
          </Link>
          <Link href="/subir" className="text-blue-600 hover:underline">
            Subir documento
          </Link>
          <Link href="/servicios" className="text-blue-600 hover:underline">
            Servicios
          </Link>
        </div>
      </div>
    </nav>
  );
}
