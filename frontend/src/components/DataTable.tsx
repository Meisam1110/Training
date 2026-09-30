import { useMemo, useRef, type ReactNode } from "react";
import { getCoreRowModel, useReactTable, type ColumnDef } from "@tanstack/react-table";
import { useVirtualizer } from "@tanstack/react-virtual";
import { toFa } from "../lib/digits";
import { Button, EmptyState, ErrorState, Skeleton } from "./ui";
import { Icon } from "./Icon";

/** Call cell/header renderers as plain functions (NOT via flexRender's <Component/>): column defs are
 *  recreated every render, and as components they would remount their subtree — dropping focus from
 *  inline selects/checkboxes on every change. Cell functions here never use hooks. */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const call = (def: unknown, ctx: any): ReactNode => (typeof def === "function" ? (def as (c: unknown) => ReactNode)(ctx) : (def as ReactNode) ?? null);

export interface TableEmpty { title: string; description?: string; action?: ReactNode }
interface Props<T> {
  caption: string; columns: ColumnDef<T, any>[]; data: T[] | undefined; getRowId: (r: T) => string;
  loading?: boolean; error?: unknown; onRetry?: () => void; empty: TableEmpty;
  sort?: string; onSort?: (s: string) => void; // "-field" = descending
  page?: number; pageSize?: number; total?: number; onPage?: (p: number) => void;
  isSelected?: (r: T) => boolean; virtualize?: boolean; maxHeight?: number; skeletonRows?: number;
}

export function DataTable<T>({ caption, columns, data, getRowId, loading, error, onRetry, empty, sort, onSort, page = 1, pageSize = 50, total, onPage, isSelected, virtualize, maxHeight, skeletonRows = 6 }: Props<T>) {
  const rows = data ?? [];
  const table = useReactTable({ data: rows, columns, getCoreRowModel: getCoreRowModel(), getRowId, manualSorting: true });
  const scroller = useRef<HTMLDivElement>(null);
  const tr = table.getRowModel().rows;
  const virt = useVirtualizer({ count: virtualize ? tr.length : 0, getScrollElement: () => scroller.current, estimateSize: () => 52, overscan: 8 });

  const colCount = table.getVisibleLeafColumns().length;
  const sortState = useMemo(() => ({ id: sort?.replace(/^-/, "") ?? "", desc: !!sort?.startsWith("-") }), [sort]);

  if (error && !rows.length) return <ErrorState error={error} onRetry={onRetry} />;
  if (!loading && !rows.length) return <EmptyState {...empty} />;

  const vItems = virtualize ? virt.getVirtualItems() : [];
  const unmeasured = virtualize && vItems.length === 0 && tr.length > 0; // no layout yet (first paint / jsdom): render a first window instead of nothing
  const padTop = virtualize && !unmeasured && vItems.length ? vItems[0]!.start : 0;
  const padBottom = virtualize && !unmeasured && vItems.length ? virt.getTotalSize() - vItems[vItems.length - 1]!.end : 0;
  const visibleRows = unmeasured ? tr.slice(0, 40) : virtualize ? vItems.map((v) => tr[v.index]!) : tr;

  const pages = total ? Math.max(1, Math.ceil(total / pageSize)) : 1;

  return (
    <>
      <div className="table-wrap" ref={scroller} tabIndex={0} role="region" aria-label={caption} style={maxHeight ? ({ ["--table-max" as string]: `${maxHeight}px` }) : undefined} aria-busy={loading || undefined}>
        <table className="table">
          <caption className="sr-only">{caption}</caption>
          <thead>
            {table.getHeaderGroups().map((hg) => (
              <tr key={hg.id}>
                {hg.headers.map((h) => {
                  const sortable = !!onSort && h.column.columnDef.enableSorting !== false && h.column.id !== "select" && h.column.id !== "actions";
                  const active = sortState.id === h.column.id;
                  return (
                    <th key={h.id} scope="col" aria-sort={active ? (sortState.desc ? "descending" : "ascending") : sortable ? "none" : undefined} style={{ inlineSize: h.column.columnDef.size ? h.column.columnDef.size : undefined }}>
                      {sortable ? (
                        <button className="th-sort" data-active={active} onClick={() => onSort!(active && !sortState.desc ? `-${h.column.id}` : active ? "" : h.column.id)}>
                          {call(h.column.columnDef.header, h.getContext())}
                          <Icon name={active ? (sortState.desc ? "chevronDown" : "sortUp") : "sort"} />
                        </button>
                      ) : call(h.column.columnDef.header, h.getContext())}
                    </th>
                  );
                })}
              </tr>
            ))}
          </thead>
          <tbody>
            {loading && !rows.length
              ? Array.from({ length: skeletonRows }, (_, i) => (
                <tr key={i} aria-hidden="true">{Array.from({ length: colCount }, (_, c) => <td key={c}><Skeleton w={c === 0 ? "70%" : "55%"} /></td>)}</tr>))
              : <>
                {padTop > 0 && <tr aria-hidden="true"><td colSpan={colCount} style={{ blockSize: padTop, padding: 0, border: 0 }} /></tr>}
                {visibleRows.map((r) => (
                  <tr key={r.id} data-selected={isSelected?.(r.original) || undefined}>
                    {r.getVisibleCells().map((c) => <td key={c.id}>{call(c.column.columnDef.cell, c.getContext())}</td>)}
                  </tr>
                ))}
                {padBottom > 0 && <tr aria-hidden="true"><td colSpan={colCount} style={{ blockSize: padBottom, padding: 0, border: 0 }} /></tr>}
              </>}
          </tbody>
        </table>
      </div>
      {onPage && total !== undefined && total > pageSize && (
        <nav className="pager" aria-label="صفحه‌بندی">
          <span>صفحهٔ {toFa(page)} از {toFa(pages)} · {toFa(total)} مورد</span>
          <span className="row">
            <Button size="sm" disabled={page <= 1} onClick={() => onPage(page - 1)}>قبلی</Button>
            <Button size="sm" disabled={page >= pages} onClick={() => onPage(page + 1)}>بعدی</Button>
          </span>
        </nav>
      )}
    </>
  );
}
