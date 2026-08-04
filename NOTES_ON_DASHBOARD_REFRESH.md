# Design note: dashboard refresh — why destroy/rebuild stays, 2026-08-04

**Decision (author, 2026-08-04): keep the destroy/rebuild approach.** Atomic
model/view updates would be more elegant and in theory more efficient, but the
performance difference is not noticeable to the end user in this application,
and destroy/rebuild is easier to maintain. Recorded so it is not re-opened on
aesthetic grounds.

Prompted by a regression during live two-machine testing: a remote assembly
modification left this client's Systems Dashboard blank (see §4).

---

## 1. The architecture, as it actually is

`MultiDashboard(QWidget)` holds a `QStackedWidget` (`self.dashboards`), one
page per dashboard name — by default six: MEL, Mass, Data Rates, Mechanical,
Thermal, System Resources. Each page is a `SystemDashboard(QTreeView)`.

`Main.dashboard` is a **read-only property**, not an attribute: it returns
`multidashboard.dashboards.widget(idx)` for the currently selected dashboard
name, or a placeholder `QLabel` when there is no project. This matters more
than it looks — see §4.

**Each dashboard builds its own model.** `MultiDashboard.add_dashboard`
(`dashboards.py:962`) does:

```python
        sys_tree_model = SystemTreeModel(self.project,
                                         dash_name=dashboard_name)
        view_model = SystemTreeProxyModel(sys_tree_model)
        dash = SystemDashboard(view_model, parent=self)
```

and the left-panel `SystemTreeView` builds its own separately
(`systemtree.py:960`), as does `powerdashboard.py:51`.

**So there is no shared `SystemTreeModel` instance.** A working assumption
while discussing this was that the dashboards viewed *the same* model the
left-panel tree uses, so their structures stayed in sync automatically. They
do not: there are roughly seven independent `SystemTreeModel` instances over
the same underlying assembly, each behind its own `SystemTreeProxyModel`.
They agree because they are each built from the same objects, not because
they share state.

## 2. Why atomic updates are harder here than the usual case

`dataChanged` / `layoutChanged` are used elsewhere in this package, mainly for
tables, and work well there — one model, one view.

Here, a single assembly change would have to be signalled on **every** live
`SystemTreeModel` instance, since each is a separate `QAbstractItemModel` with
its own internal `Node` tree. The options are therefore:

- emit on all of them, which needs something that knows the full set — no such
  registry exists today; or
- introduce a genuinely shared model first, which is the larger change, and
  changes the meaning of the per-dashboard `dash_name` the models are built
  with.

Neither is "just emit `dataChanged`". That is the substance of the decision,
and it is a stronger reason than the ones originally given.

Additional context from the author: the assembly tree is **not directly
editable** — it is a view of structure that is changed elsewhere (drag/drop
onto diagrams, context menus on blocks) — so the usual driver for atomic
updates, keeping an editing cursor and selection stable under the user's
hands, does not apply with the same force.

## 3. What must stay destroy/rebuild regardless

Switching projects. The models are constructed *from* a project
(`SystemTreeModel(self.project, ...)`), so a project change is a rebuild by
construction, not an update.

## 4. The latent defect this exposed, and the lesson

`refresh_tree_views()` carried a block that claimed to destroy the existing
dashboard:

```python
                if getattr(self, 'dashboard', None):
                    dashboard_panel_layout.removeWidget(self.dashboard)
                    self.dashboard.setAttribute(Qt.WA_DeleteOnClose)
                    self.dashboard.hide()
                    self.dashboard.parent = None      # (before the fix)
                    self.dashboard.close()
                    self.dashboard = None
                    self.dashboard_rebuilt = False
```

Two things were wrong with it, and they compounded:

1. `dashboard` is a **property with no setter**, so `self.dashboard = None`
   raised `AttributeError` every single time. The surrounding bare
   `except: pass` swallowed it, and the line after it never ran. The block had
   never done what it said.
2. `self.dashboard` is not this window's widget — it is a page owned by the
   `QStackedWidget` inside `MultiDashboard`.

While `.parent = None` was a no-op (it shadowed `QWidget.parent` rather than
reparenting), the page survived and nobody noticed. When that idiom was
corrected to `setParent(None)`, the detach became real, `close()` with
`WA_DeleteOnClose` genuinely destroyed the page, and the `MultiDashboard` was
left holding a corpse — dashboard blank, and staying blank.

**Removed rather than repaired**: the `MultiDashboard`'s lifetime belongs to
`rebuild_dashboard()`, which `refresh_tree_views()` already calls, and the
identical teardown *inside* that method had already been commented out.

The lesson worth carrying: a teardown that has been silently failing looks
exactly like a teardown that works, until something makes it effective. The
bare `except: pass` is what let it hide for however long it had been there.

## 5. Could they share one model after all? — no, and here is the reason

They did once: the commented-out line in `pangalaxian.py` still reads

```python
            # self.dashboard = SystemDashboard(self.sys_tree.model(),
                                             # parent=self)
```

— the single-dashboard version, viewing the left-panel tree's own model. The
per-dashboard models arrived with the `QStackedWidget` rewrite.

**The reason they had to (author, 2026-08-04): in Qt's model/view, the columns
belong to the model.** `columnCount()` and `data(index)` are model APIs, so
views that must show *different columns* need different models. The dashboards
differ in exactly that way — `dash_name` selects the column set — so separate
models follow directly. Calling it a defect of the concept is fair: the row
structure is identical across all of them and is the expensive part, yet it
has to be duplicated seven times to vary the columns.

*An earlier draft of this section claimed sharing "does look viable" via
`QSortFilterProxyModel.filterAcceptsColumn()`. That was too optimistic and is
corrected here.* The hook does exist and would let each proxy present a subset
of a union model's columns, but it does not dissolve the problem:

- **Column sets are mutable per dashboard.** Columns are added by dropping a
  parameter or data element onto a dashboard, appending to
  `prefs['dashboards'][dash_name]` (`dashboards.py:276, 295, 315`), and
  removed through the header context menu. With a shared model each such
  action would have to extend the union *and* adjust only that dashboard's
  filter — machinery that does not exist now.
- **Column order is per dashboard.** `prefs['dashboards'][dash_name]` is an
  ordered list and `cols` returns it in order. A proxy filter preserves the
  *source* order and cannot permute, so per-dashboard ordering could not be
  expressed by filtering alone. (Header drag-reordering via `sectionMoved` is
  wired but commented out — it crashes — so this is latent rather than active,
  but the pref order still drives display order.)
- **"System Power Modes" is not a column subset at all.** Its columns are
  project modes from `mode_defz`, with special-cased branches in `data()`, so
  it could never be a filtered view of a parameter-column model.

So separate models are a reasonable response to a real constraint, not an
oversight — which also means §2's "signal every instance" is not a problem to
be engineered away by sharing. The decision in §1 stands on this rather than
on maintainability alone.
