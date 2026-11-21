// The short header of every page: what the page is for and what it reads (the live stream, uploaded files or both). Words live in
// validation/guide.ts so they are tested. Also the shared "pick a station" empty state, which opens the header's picker.
import { PAGE_INFO, OPEN_PICKER_EVENT, readsLine } from '../validation/guide';
import type { PageId } from '../validation/shell';
import { EmptyState } from '../design-system/components/EmptyState';

export const openStationPicker = () => window.dispatchEvent(new Event(OPEN_PICKER_EVENT));

export function PageIntro({ page }: { page: PageId }) {
  const info = PAGE_INFO[page];
  return (
    <div className="bg-[#FFFFFF] border border-[#D3DCE7] rounded-xl px-4 py-3 shadow-sm" data-testid="page-intro">
      <h2 className="text-sm font-bold text-slate-900">{info.title}</h2>
      <p className="text-xs text-slate-700 mt-0.5">{info.what}</p>
      <p className="text-[11px] font-mono text-slate-500 mt-1">{readsLine(page)}</p>
    </div>
  );
}

/** Shown on a station page while no station is selected: says why and offers the picker. */
export function NeedStation({ what }: { what: string }) {
  return (
    <EmptyState
      title="No station selected"
      description={`${what} Pick a station first: this page shows only the station chosen in the header.`}
      actionLabel="Pick a station"
      onAction={openStationPicker}
    />
  );
}
