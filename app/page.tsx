import { redirect } from 'next/navigation';

export default function Home() {
  const now = new Date();
  const yearMonth = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
  redirect(`/mes/${yearMonth}`);
}
