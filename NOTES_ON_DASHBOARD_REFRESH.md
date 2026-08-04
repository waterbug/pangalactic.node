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

## 5. If this is ever revisited

Start by establishing whether a single shared `SystemTreeModel` per project is
viable given `dash_name`, rather than by adding `refresh()` methods. Neither
`SystemDashboard` nor `MultiDashboard` has one today, and adding one that
rebuilds internally would be destroy/rebuild wearing a different name.
