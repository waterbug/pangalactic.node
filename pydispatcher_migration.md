# pangalactic.node — completing the pydispatcher migration, 2026-08-03

Survey before edits, at the author's direction. `pyqtSignal` is a legacy
detour in this package: it was adopted after an elusive bug was mistakenly
attributed to pydispatcher, and by the time the real cause was found too many
signals had been converted for reverting to be worth prioritising. The target
is pydispatcher throughout.

Prioritised ahead of the component-mode divergence
(`pangalaxian_remaining_chunks_review.md` #4) because that finding's durable
fix is *"finish the migration and delete `del_object`"* — the divergence is a
symptom, not the disease.

---

## 1. The boundary: what must stay `pyqtSignal`

**`threads.py`'s four `WorkerSignals` — `finished`, `error`, `result`,
`progress` — must not be converted.** They are the only signals in the
package that cross a thread boundary, and that is precisely what Qt signals do
and pydispatcher does not.

**Verified by execution.** A `QRunnable` emitting each kind from a threadpool
thread, with the receiver reporting which thread it ran in:

| mechanism | sent from | receiver ran in |
|---|---|---|
| `pyqtSignal` | `Dummy-1` (worker) | **`MainThread`** — Qt marshals it |
| `pydispatcher` | `Dummy-1` (worker) | **`Dummy-1`** — called synchronously |

Converting these would run `update_chunk_progress` — which calls
`self.chunk_progress.setValue(n)` on a live `QProgressDialog` — in a worker
thread. Touching Qt widgets off the GUI thread is undefined behaviour.

Everything else in the package is same-thread GUI signalling and is
convertible.

## 2. Why the migration is worth doing: the relay chain

The author's rule of thumb is *"make signals as specific as possible and avoid
chaining"*. `pyqtSignal`'s point-to-point model makes chaining unavoidable: a
signal can only reach an object that holds a reference to the emitter, so a
leaf widget cannot notify `Main` directly. Every level in between has to hand
it on.

`obj_modified` is the clearest case. Four separate classes carry a handler
whose entire body re-emits the same signal one level up:

```python
    def on_obj_modified(self, oid):
        self.obj_modified.emit(oid)          # systemtree, libraries x2
```
```python
    def on_pgxo_mod_object_signal(self, oid):
        ...
        self.obj_modified.emit(oid)          # filters
```

so a single edit travels:

    parameter form / pgxn form
        -> PgxnObject.on_object_mod
            -> SystemTreeView / LibraryWidget / FilterPanel .on_obj_modified
                -> Main.on_mod_object_qtsignal
                    -> Main.on_mod_object_signal

Three hops of pure relay to reach a handler that could have received it
directly. Under pydispatcher the leaf sends `'modified object'` once and
`Main` hears it — the intermediate handlers cease to exist. **That is the
substance of this migration**: it removes relay code, not just a signalling
API.

## 3. The pyqtSignals shadow dispatcher signals that already exist

`pangalaxian.py:455-470` sets both up, ten lines apart:

```python
        # connect pyqtSignals ...
        self.deleted_object.connect(self.del_object)
        self.new_object.connect(self.on_new_object_qtsignal)
        self.mod_object.connect(self.on_mod_object_qtsignal)
        # connect dispatcher signals ...
        dispatcher.connect(self.on_new_object_signal, 'new object')
        dispatcher.connect(self.on_mod_object_signal, 'modified object')
```

Each pyqtSignal has a dispatcher twin, and the `*_qtsignal` handlers are pure
adapters that convert an oid to an object and delegate to the dispatcher
handler:

```python
    def on_mod_object_qtsignal(self, oid):
        obj = orb.get(oid)
        if obj:
            cname = obj.__class__.__name__
            self.on_mod_object_signal(obj=obj, cname=cname)
```

So the two paths already converge. Migration is mostly *deletion*: have the
emitters send the dispatcher signal, then remove the pyqtSignal, its adapter,
and the relays.

### 3a. Both are fired at the same site, so the handler runs twice

At every `PgxnObject` emit site, the dispatcher signal and the pyqtSignal are
sent back to back:

```python
                dispatcher.send(signal='modified object', obj=self.obj)
                self.obj_modified.emit(self.obj.oid)          # 627
```
```python
    def on_object_mod(self, oid):
        self.obj_modified.emit(oid)
        dispatcher.send(signal='modified object', obj=self.obj)   # 1318
```
```python
            dispatcher.send(signal="modified object", obj=self.obj,
                            cname=cname)
            self.obj_modified.emit(self.obj.oid)                   # 2642
```

Both reach `Main.on_mod_object_signal` — once directly, once through the
relay chain and the adapter. **`on_mod_object_signal` therefore appears to run
twice for a single edit in the object editor**, and it is the handler that
calls `vger.save`.

This is the same shape as the duplicate-RPC bug found in the admin tool
(`pangalaxian_remaining_chunks_review.md` #2).

**CONFIRMED at runtime (author, 2026-08-03):** the log shows a doubled
`* on_mod_object_signal()` and, consequently, duplicate `vger.save()` rpcs
per edit. That makes `obj_modified` a bug fix rather than cleanup, and it was
done first (see §8).

## 4. What the broadcast model changes

pydispatcher is many-to-many: a receiver hears a signal from *any* sender, and
a sender reaches *all* receivers. Four consequences to manage per signal:

1. **Sender scoping.** `dlg.obj_modified.connect(...)` hears only that dialog;
   `dispatcher.connect(rcv, 'modified object')` hears every emitter. Where
   per-instance behaviour is required, `dispatcher.connect(rcv, sig,
   sender=obj)` restores it — **verified by execution**: unscoped received
   from both senders, `sender=`-scoped received only from the one.
2. **Cycles.** Point-to-point signals cannot easily loop; broadcast ones can,
   because an emitter that is also a receiver hears itself. The author has
   been careful about this, and a cycle is usually obvious at runtime, but
   each conversion should check whether the sender is also connected.
3. **Weak references.** pydispatcher holds receivers weakly. A bare function
   or lambda connected inline is garbage collected immediately and never
   fires — silently. Receivers must be bound methods of objects that stay
   alive. (This already produced a false-passing test; see the note on
   `DispatcherSpy` in `test/conftest.py`.)
4. **No automatic disconnection.** Neither mechanism disconnects on widget
   destruction, which is what produced the admin-tool accumulation. Converting
   does not fix that by itself.

## 5. Inventory

29 declarations, 17 distinct names.

| signal | declared in | disposition |
|---|---|---|
| `finished`, `error`, `result`, `progress` | `threads.py` | **KEEP** — cross-thread |
| `mod_object` | `pangalaxian.py:238` | **DELETE** — never emitted; its connect at 458 is dead |
| `activity_edited` | `pgxnobject.py:887` | **DELETE** — emitted at 2645, no receiver anywhere |
| `obj_modified` | `pgxnobject.py` x2, `libraries.py` x2, `filters.py`, `systemtree.py` | **CONVERGE** on `'modified object'`; deletes 4 relay handlers |
| `deleted_object` | `admin.py` x2, `pangalaxian.py:236` | **CONVERGE** on `'deleted object'`; unlocks review #4 |
| `new_object` | `admin.py:658`, `pangalaxian.py:237` | **CONVERGE** on `'new object'` |
| `delete_obj` | `libraries.py:334`, `filters.py:568` | convert |
| `units_set` | `dashboards.py:41`, `dialogs.py` x2 | convert |
| `refresh_admin_tool` | `pangalaxian.py:242` | convert |
| `remote_frozen`, `remote_thawed` | `pangalaxian.py:240-241` | convert |
| `toggle_library_size` | `libraries.py:335` | convert |
| `hw_fields_edited` | `dialogs.py:376` | convert |
| `rqt_parm_mod` | `dialogs.py:1383` | convert |

*Caveat on the inventory:* signals passed around as objects are invisible to a
name-based search — `progress` appears to have no emitter because it is
emitted through the `progress_signal` kwarg the `Worker` injects. Any signal
handed to another function as a parameter needs checking by hand.

## 6. Proposed order

1. **The two dead ones** (`mod_object`, `activity_edited`) — pure deletion,
   no behaviour change.
2. **The leaf signals** with one emitter and one receiver —
   `toggle_library_size`, `hw_fields_edited`, `rqt_parm_mod`. Smallest real
   conversions; establish the pattern.
3. **`remote_frozen` / `remote_thawed`, `units_set`, `refresh_admin_tool`** —
   one-to-few, self-contained.
4. **`obj_modified`** — the workhorse, and where the relay chain dies.
   Confirm 3a first.
5. **`new_object` / `delete_obj` / `deleted_object`** — last, because
   `deleted_object` is entangled with `del_object` and therefore with review
   #4. Finishing it should let `del_object` be deleted and the divergence
   resolved by construction.

## 7. Found in passing (not part of the migration)

**`threads.py`'s `error` signal is emitted and connected nowhere.** If the
function running in the worker raises, `Worker.run` catches it, emits `error`
into the void, and then emits `finished` regardless. At the one live call site
that means a failed file read closes the progress dialog and lets the upload
proceed with a partial or empty `chunks_to_upload` — a silently truncated
upload. The threading structure around it is otherwise correct: `chunk_file`
touches no widgets from the worker thread, and both connected receivers arrive
on the main thread.

---

## 8. Step 1 as built: `obj_modified` (2026-08-03)

Taken first rather than fourth, once the double-fire was confirmed at runtime.

**Removed**, across five modules:

| | |
|---|---|
| `obj_modified` declarations | 6 — `pgxnobject.py` x2, `libraries.py` x2, `filters.py`, `systemtree.py` |
| per-instance `.connect(...)` wirings | 17 — 9 in `pangalaxian.py`, 4 in `libraries.py`, 3 in `pgxnobject.py`, 1 in `systemtree.py` |
| relay handlers (`on_obj_modified` etc.) | 4 — `systemtree.py`, `libraries.py` x2, `pgxnobject.on_object_mod` |
| redundant `.emit(...)` calls | 3 — every one had `dispatcher.send('modified object')` on an adjacent line |
| the oid→obj adapter | `Main.on_mod_object_qtsignal` |
| dead signal | `mod_object` — declared and connected, never emitted |

Nothing replaced them: `'modified object'` was already being sent at every
origin and already connected in `Main`. The relay existed only because a
pyqtSignal cannot reach a non-referencing receiver.

**The one relay that was not pure** was `FilterPanel`'s: it called
`sourceModel().mod_object(oid)` before re-emitting. That work now hangs off
the dispatcher signal directly (`FilterPanel.on_mod_object_signal`, connected
in `__init__`). Worth stating why it is not redundant with the equivalent
receiver in `ObjectTableView`: `FilterPanel` uses `ProxyView`, a different
class, so nothing else was updating its model.

Because the receiver is now broadcast rather than per-dialog, it also guards
against a `'modified object'` send that carries no object — it sees every
send in the process now, not just its own dialog's.

`systemtree.py`'s `pyqtSignal` import went with the last declaration.

**Tests:** `test/test_signal_migration.py` — a guard against the relay
pattern returning (matching *use*, not mentions in prose), a check that the
adapter is gone, and two behavioural tests for the rewired `FilterPanel`.
Three of the four fail against the pre-migration code, including the
`FilterPanel` one — the piece that could have broken silently.

**Validated against the running app (author, 2026-08-03).** All four risk
areas exercised:

| exercised | result |
|---|---|
| filterable tables update in place on edit (the rewired non-pure relay) | ok |
| dropping a data element onto an object in the editor | ok |
| editing from the system tree ("View or edit this object", a *modal* dialog) and from library panels | ok |
| one `on_mod_object_signal()` and one `vger.save()` per edit | ok |

The modal case is the strictest: under the old wiring the edit reached `Main`
through the tree's relay, and it now has to arrive on the dispatcher signal
while a modal dialog is up. It does.

*(Interaction note for future test instructions: an object is edited from the
tree by right-click -> "View or edit this object", not by double-clicking.)*

**Still to do:** steps 2, 3 and 5 of §6 — the leaf signals, the one-to-few
signals, and `new_object`/`delete_obj`/`deleted_object` (which unlocks review
#4). `activity_edited` (dead, no receiver) is still to be removed.

---

## 9. Step 2 as built: the leaf signals (2026-08-03)

`toggle_library_size`, `hw_fields_edited`, `rqt_parm_mod`, plus the dead
`activity_edited`. Unlike step 1 these have no dispatcher twin already in
place, so each needed a signal name chosen and a receiver connected — real
conversions rather than deletions.

| signal | now | receiver connects in |
|---|---|---|
| `toggle_library_size` | `'toggle library size'` | `Main.__init__` |
| `hw_fields_edited` | `'hw fields edited'` | `FilterPanel.__init__` |
| `rqt_parm_mod` | `'rqt parm mod'` | `RqtManager.__init__` |
| `activity_edited` | deleted — emitted, no receiver anywhere | — |

Live `pyqtSignal` declarations: **22 → 18**, of which 4 are `threads.py`'s
cross-thread signals that stay. `pgxnobject.py`'s `pyqtSignal` import went
with its last declaration.

Receivers gained keyword defaults (`oid=None`) because pydispatcher passes
arguments as keywords where a pyqtSignal passed them positionally.

**Deliberately mechanical.** Each conversion preserves current behaviour
exactly; nothing was "improved" on the way past. Two things noticed that are
*not* changed here, because they are behaviour questions rather than
migration steps — see §10.

### A duplication removed in passing

`FilterPanel.on_mod_object_signal`, added in step 1, had inlined the body of
the existing `FilterPanel.mod_object`. It now calls it.

## 10. Behaviour questions surfaced by step 2 (not acted on)

1. **`HWFieldsDialog` edits never reach the repository.** `on_save` calls
   `orb.save([self.hw_item])` and signals the table to refresh, but no
   `'modified object'` is sent, so `Main.on_mod_object_signal` never runs and
   `vger.save` is never called. The dispatcher send is present in the source
   but **commented out**, directly beneath the emit. Sending it would fix the
   sync but is a behaviour change, and the commented-out line suggests it was
   disabled deliberately at some point — so it is left exactly as it was, with
   the reason marked at the site. There is one caller
   (`filters.py:1045`), so the blast radius is small either way.

2. **`rqt_parm_mod` may now be redundant.** Its receiver only acts when
   offline (`if not state.get('connected')`), and its caller already sends
   `'modified object'` on `Accepted` — which, since step 1, `FilterPanel`
   receives and acts on regardless of connection state. If that reasoning
   holds at runtime, the signal and its handler can simply be deleted. Not
   done on reasoning alone.

---

## 11. Step 3 as built: the one-to-few signals (2026-08-03)

| signal | now | receiver connects in |
|---|---|---|
| `units_set` | `'units set'` | `Main.__init__` |
| `remote_frozen` | `'remote frozen'` | `PgxnObject.__init__` |
| `remote_thawed` | `'remote thawed'` | `PgxnObject.__init__` |
| `refresh_admin_tool` | `'refresh admin tool'` | `do_admin_stuff`, per dialog |

Live `pyqtSignal` declarations: **18 → 11**. Of those 11, four are
`threads.py`'s cross-thread signals that stay, and the remaining seven are
step 5's (`deleted_object` x3, `new_object` x2, `delete_obj` x2).
`dashboards.py` and `dialogs.py` lost their now-unused `pyqtSignal` imports.

**`units_set` was a third relay chain**, and again the target name was already
chosen and sitting commented out above the emit:

```python
        # dispatcher.send('units set')
        self.units_set.emit()
```

`UnitPrefsDialog` is the only origin. `Dashboard` and `PrefsDialog` each
carried a `set_units`/`set_preferred_units` method that opened it, wired
itself to the result, and re-emitted an identically-named signal of its own,
purely so it could reach `Main`. Both relays are gone; the dialog sends
`'units set'` and `Main` hears it.

**`remote_frozen`/`remote_thawed` inverted a dependency.** `Main` was wiring
these into each `PgxnObject` it created, at two separate construction sites,
so it had to remember to do so every time. Each `PgxnObject` now connects its
own receivers and ignores oids that are not its object's. Note the two
receivers take differently-named arguments (`frozen_oids=` and `oids=`), so
the sends match each one rather than sharing a convention.

**`refresh_admin_tool` was the one with a teardown.** It is the signal from
remaining-chunks review #2, where every re-open left another live dialog
connected. The explicit `disconnect` added by that fix is preserved and is now
symmetric — both it and the `'deleted object'` disconnect next to it go
through pydispatcher, which does not disconnect on destruction either.
Converting a signal that has a teardown means converting the teardown.
