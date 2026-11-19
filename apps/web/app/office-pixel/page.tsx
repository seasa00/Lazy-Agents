import OfficeExperience from '@/features/office-pixel/OfficeExperience';

export default function OfficePixelPage() {
  return <div style={{ position: 'fixed', inset: 0, zIndex: 10000 }}><OfficeExperience /></div>;
}
