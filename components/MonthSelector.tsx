'use client';

import { useRouter } from 'next/navigation';

interface Props {
  current: string; // "2026-03"
}

export default function MonthSelector({ current }: Props) {
  const router = useRouter();

  function navigate(delta: number) {
    const [y, m] = current.split('-').map(Number);
    const date = new Date(y, m - 1 + delta, 1);
    const ym = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`;
    router.push(`/mes/${ym}`);
  }

  return (
    <div className="flex items-center gap-2">
      <button
        onClick={() => navigate(-1)}
        className="px-3 py-1 border rounded hover:bg-gray-100 text-sm"
      >
        &larr; Anterior
      </button>
      <button
        onClick={() => navigate(1)}
        className="px-3 py-1 border rounded hover:bg-gray-100 text-sm"
      >
        Siguiente &rarr;
      </button>
    </div>
  );
}
