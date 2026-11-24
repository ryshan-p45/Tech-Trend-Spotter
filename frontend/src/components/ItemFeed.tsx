import { useState } from 'react'
import { useInfiniteQuery } from '@tanstack/react-query'
import { listItems } from '../api/client.ts'
import type { SourceType } from '../api/types.ts'
import ItemCard from './ItemCard.tsx'
import Panel from './Panel.tsx'
import StateMessage from './StateMessage.tsx'

// Tabs shown above the feed; `undefined` = every source type
const TABS: { label: string; sourceType: SourceType | undefined; emptyMessage: string }[] = [
  { label: 'All', sourceType: undefined, emptyMessage: 'Nothing collected yet. Press "Run collection" to fetch the latest items.' },
  { label: 'Advisories', sourceType: 'advisory', emptyMessage: 'No advisories collected yet. They come from CISA KEV and GitHub Advisories on the next run.' },
  { label: 'News', sourceType: 'web', emptyMessage: 'No news articles collected yet. They come from the RSS feeds on the next run.' },
  { label: 'Discussions', sourceType: 'social', emptyMessage: 'No discussions collected yet. They come from Hacker News on the next run.' },
]

const PAGE_SIZE = 20

// Newest collected items, filterable by type, loaded a page at a time
function ItemFeed() {
  const [activeTab, setActiveTab] = useState(0)
  const tab = TABS[activeTab]

  const items = useInfiniteQuery({
    queryKey: ['items', tab.sourceType ?? 'all'],
    queryFn: ({ pageParam }) => listItems({ sourceType: tab.sourceType, limit: PAGE_SIZE, cursor: pageParam }),
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) => lastPage.pagination.next_cursor,
  })
  const rows = items.data?.pages.flatMap((page) => page.data) ?? []

  return (
    <Panel title="Latest signals" subtitle="Everything collected, newest first">
      <div role="tablist" aria-label="Filter by source type" className="mb-4 flex flex-wrap gap-1">
        {TABS.map((option, index) => (
          <button key={option.label} type="button" role="tab" aria-selected={index === activeTab}
            onClick={() => setActiveTab(index)}
            className={`px-3 py-1 text-xs tracking-wider uppercase transition-colors ${
              index === activeTab
                ? 'bg-hud-cyan/15 text-hud-cyan shadow-[inset_0_-2px_0_var(--color-hud-cyan)]'
                : 'text-hud-muted hover:text-hud-text'
            }`}>
            {option.label}
          </button>
        ))}
      </div>

      <div role="tabpanel" aria-label={`${tab.label} items`}>
        {items.isPending && <StateMessage kind="loading" message="Loading items…" />}
        {items.isError && rows.length === 0 && <StateMessage kind="error" message={items.error.message} />}
        {items.isSuccess && rows.length === 0 && <StateMessage kind="empty" message={tab.emptyMessage} />}
        {rows.length > 0 && (
          <ul className="flex flex-col gap-4">
            {rows.map((item) => <li key={item.item_id}><ItemCard item={item} /></li>)}
          </ul>
        )}
        {items.hasNextPage && (
          <button type="button" className="hud-button mt-5" onClick={() => items.fetchNextPage()}
            disabled={items.isFetchingNextPage}>
            {items.isFetchingNextPage ? 'Loading…' : 'Load more'}
          </button>
        )}
        {/* A failed "Load more" keeps the items already shown and explains what to do */}
        {items.isError && rows.length > 0 && (
          <StateMessage kind="error" message={`Couldn't load more items: ${items.error.message}`} />
        )}
      </div>
    </Panel>
  )
}

export default ItemFeed
