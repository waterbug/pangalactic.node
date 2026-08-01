# pangalactic.node review — `admin.py` (the admin tool), 2026-08-01

Sixth installment of the `pangalactic.node` review, and the first pass over
`admin.py` (858 lines), which had not been reviewed at all. It covers
`RADropLabel`, `PersonSearchDialog`, `AddPersonDialog` and `AdminDialog`.

Prompted by the author's observation that "add user is broken unless LDAP is
being used" — which is correct, and is finding #2 below. The pass turned up a
more serious problem alongside it: **role assignment deletions never reach the
repository** (#1).

Context taken as given (author): `gargleblaster` is a local-environment-
specific wrapper, so its hardcoded `ldap_schema` is by design, not a defect.
That matters for #3, where the consequence is a broken contract between
`admin.py` and `pangalaxian.py` rather than a bug in the wrapper.

Findings were verified by execution except where marked.

---

## Findings (most severe first)

### 1. Deleting a RoleAssignment never reaches the repository
`pangalactic/node/admin.py:85-93` (`RADropLabel.delete_role`), `130-231`
(`RADropLabel.dropEvent`), with `pangalaxian.py:475` and `4770` (`del_object`)

**Role assignments are permissions**, so this is the most consequential
finding in the file.

`delete_role` deletes the object locally and announces it on the dispatcher:
```python
        ra_oid = self.ra.oid
        orb.delete([self.ra])
        dispatcher.send(signal='deleted object', oid=ra_oid,
                        cname='RoleAssignment')
        # self.deleted_object.emit(ra_oid, 'RoleAssignment')
```
The `deleted_object.emit(...)` is **commented out** — at all three sites in
this file (93, 184, 226). That matters because of how the two notification
paths differ in `pangalaxian.py`:

| path | handler | calls `vger.delete`? |
|---|---|---|
| dispatcher `'deleted object'` | `on_deleted_object_signal` (475) | **no** — GUI updates only |
| `deleted_object` pyqtSignal | `del_object` (4770) | **yes** |

`AdminDialog.deleted_object` is connected to `Main.del_object` in
`do_admin_stuff`, but the only thing that emits it is
`AdminDialog.on_deleted_object`, which is only connected to
`RADropLabel.deleted_object` — which is never emitted. **The entire chain to
`vger.delete` is dead**, so a role assignment deleted through the admin tool
is removed locally and the repository is never told. On the next
`sync_project` the server returns the RoleAssignment as an object the client
does not have, and it is restored.

**The drag-and-drop case is worse.** `RADropLabel.dropEvent` implements
"change the role/person on this assignment" as *create a new RA, then delete
the old one*:
```python
                orb.save([ra])
                dispatcher.send(signal='new object', obj=ra)     # -> vger.save
                deleted_oid = self.ra.oid
                orb.delete([self.ra])
                dispatcher.send(signal='deleted object', ...)    # -> nothing
```
The create is pushed (`on_new_object_signal` → `on_mod_object_signal` →
`vger.save`); the delete is not. So after re-assigning a role by drag and
drop, the repository holds **both** assignments — and the person keeps the
role the administrator meant to take away, while the admin tool shows only the
new one.

**STATUS: FIXED.** All three `deleted_object.emit(...)` lines are restored
(`delete_role` and both `dropEvent` branches), with a note at each explaining
why *both* notifications are required: the dispatcher signal drives the local
GUI updates and the tool refresh, the pyqtSignal is the only path to
`vger.delete`. **Verified by execution** with real PyQt signals and a real
pydispatcher, mirroring the wiring:

| | GUI updated | `vger.delete` called |
|---|---|---|
| pre-fix | yes | **no — repository never told** |
| post-fix | yes | yes |

**Known cost, deliberately accepted for now:** `refresh_roles` now runs twice
per deletion — once via `do_admin_stuff`'s
`dispatcher.connect(admin_dlg.refresh_roles, "deleted object")`, and once via
`on_deleted_object`. Wasteful but harmless, and correctness came first. The
right resolution is to converge the two notification mechanisms (see the
smaller items below), which is part of the pydispatcher/pyqtSignal migration
rather than something to settle here.

*(Note on the verification: the harness above does not model the
`do_admin_stuff` dispatcher connection, so its "admin refreshed: False" for
the pre-fix case is an artifact of the harness — the tool did refresh before
this change, via that route. What it did not do was tell the repository.)*

### 2. There is no way to create a user without LDAP
`admin.py:233-387` (`PersonSearchDialog`), `389-505` (`AddPersonDialog`)

`AddPersonDialog` — the only place a Person and their public key can be
created — is reachable **only** by clicking a row in a search result:

```
AdminDialog.ldap_search_button -> PersonSearchDialog -> (search)
    -> on_search_result -> results table -> person_selected
        -> add_person_panel.setVisible(True) -> on_add_person
            -> AddPersonDialog
```

Every step needs records to click on, so the three cases are:

- **LDAP configured and available** — works as designed.
- **"Known Users Only"** — `vger.search_ldap`'s `known_users` branch returns
  `orb.get_by_type('Person')`, i.e. everyone *already in the repository*
  (note it ignores the search criteria entirely). This can attach a public key
  to an **existing** user, but cannot create anyone.
- **No LDAP** — `search_ldap` returns `[LDAP_NOT_AVAILABLE, []]`, so the table
  has no rows, `person_selected` never fires, the "Add Person" panel stays
  hidden, and `AddPersonDialog` is unreachable.

So it is specifically **creating a new user** that has no non-LDAP route. The
dialog is even titled "Create User" while being reachable only by selecting
someone who already exists.

Given that an LDAP directory is now expected to be the exception rather than
the rule, this needs a direct path. Proposed shape, per the author: a **"New
User"** action opening `AddPersonDialog` with blank fields, requiring a
minimum of

| field | required | why |
|---|---|---|
| `id` (userid) | **yes** | becomes the `authid` in `principals.db`; `add_person` inserts `(public_key, data['id'], 'user')`, so without it there is nothing to authenticate as |
| `last_name`, `first_name` | yes | the person's name |
| organization | yes | `add_person` auto-creates an `Organization` when the name is unknown |
| `public_key` | yes | without it the user cannot log in at all |
| `mi_or_name`, `email` | no | |

**Two things must be fixed as part of that change, or it will not work:**
see #3 and #4.

**STATUS: FIXED (with #7).** `AdminDialog` now has a **"New User"** button —
unconditional, independent of LDAP — which opens `AddPersonDialog` with blank
fields. `AddPersonDialog` no longer builds its form from `ldap_schema` (that
is #7); it uses a module-level `PERSON_FIELDS` spec keyed by `Person`
attribute, with the required ones marked `*` in the form:

| field | required |
|---|---|
| `id` (User ID), `first_name`, `last_name`, `org_code` (Organization) | yes |
| `mi_or_name`, `employer_name`, `email` | no |

`org_code` and `employer_name` are the names `vger.add_person()` expects — it
resolves each to an `Organization` by id / by name, creating one if unknown.

`on_save` now validates before dispatching:
1. **required fields present**, listing any that are missing;
2. **the user id is unique** — it becomes the `authid` that both the
   repository and the crossbar authenticator identify the user by, so a
   collision is refused (an existing person being re-saved is exempted via
   their oid);
3. **no public key is allowed but must be deliberate** — a Yes/No
   confirmation states plainly that the user will be created and will *not*
   be able to log in until a key is added. Blocking outright would have
   broken the legitimate "create now, add the key later" flow, and saying
   nothing is what made #4's failure mode so hard to diagnose.

The dialog also now carries `oid` through explicitly rather than depending on
the deployment's `ldap_schema` happening to map something to it — otherwise a
person selected from a search could be duplicated instead of updated.

**Verified by execution**, with **no `ldap_schema` configured at all**:

| case | dispatched `'add person'` |
|---|---|
| blank dialog constructed (would previously raise `TypeError`) | — constructs, 7 fields |
| required fields missing | no |
| user id `zaphod` already taken | no |
| complete, with a valid public key | yes |
| no public key, confirmation answered **No** | no |
| no public key, confirmation answered **Yes** | yes |
| LDAP-supplied data | form populated, `oid` carried, title "Add User" |

**Verified live against marvin (2026-08-01).** The payload this dialog
produces — driven through the real `on_get_key()` and `on_save()`, with **no
`ldap_schema` configured** — was sent to the live repository as
`vger.add_person`, which returned `pk_added=True` and created the Person; the
new user then authenticated with their freshly generated private key and
appeared in the roster as an active user.

**That live run is also what found the two server-side defects** recorded in
`pangalactic.vger/vger_review.md` ("Found by live testing against marvin"):
`add_person` never generated an `oid`, so it could not create a Person at all
without one arriving from LDAP; and nothing enforced that the userid — which
becomes the `authid` — was unique. Neither was reachable by reading the client
code, and neither would have been caught by the unit suite. **The client-side
work in this document was necessary but not sufficient**: without those two
fixes the "New User" button could not have worked regardless.

### 3. `AdminDialog` creates the LDAP button conditionally; `pangalaxian` connects to it unconditionally
`admin.py:554-557` with `pangalaxian.py`'s `do_admin_stuff`

```python
        # if we have an ldap_schema, add an LDAP search button
        if config.get('ldap_schema'):
            self.ldap_search_button = SizedButton('Search for a Person')
            self.right_vbox.addWidget(self.ldap_search_button)
```
but the caller does, with no guard:
```python
        self.admin_dlg.ldap_search_button.clicked.connect(self.open_person_dlg)
```
With no `ldap_schema` in config the attribute does not exist and **opening the
admin tool raises `AttributeError`** — the whole tool, not just the button.

This is masked today because `gargleblaster/__main__.py:52` always sets
`app_config['ldap_schema']`. That is correct for gargleblaster (an
environment-specific wrapper), but it means the defect is invisible here and
live for any other wrapper, or for `pangalaxian.py` run directly. Note also
the inverse consequence: because the wrapper always sets a schema, the LDAP
search button is always shown *even when there is no LDAP directory*, which
is exactly the confusing state finding #2 describes.

**STATUS: FIXED.** `do_admin_stuff` now guards with
`getattr(self.admin_dlg, 'ldap_search_button', None)`. The conditional
creation in `AdminDialog` is kept deliberately — the button *should* be absent
when LDAP is not in use; the defect was the caller assuming it. **Verified by
execution**: pre-fix, a dialog without the attribute raises `AttributeError`
and the tool cannot open; post-fix it opens.

### 4. The public key is neither stripped nor validated — a trailing newline silently prevents login
`admin.py:435-496` (`AddPersonDialog.on_get_key`), `498-505` (`on_save`)

```python
                f = open(fpath)
                data = f.read()
                f.close()
...
        if data:
            self.public_key = data
```
The file contents are used verbatim. `vger.add_person` inserts that string
into `principals.db`, and `authenticator.py` matches it with
`SELECT authid, role FROM users WHERE pubkey = ?` against the key from the
WAMP handshake — a bare 64-character hex string. **Verified by execution**
against a real sqlite db:

| key file | authenticator lookup |
|---|---|
| no trailing newline | matches |
| **trailing newline** | **fails — the user cannot log in** |

`gen_keys()` writes `public.key` without a newline, so an app-generated file
is clean; a key that has been through an editor, an email, or a copy-paste
almost certainly is not. The failure is completely silent — the person is
added, the administrator is told it succeeded, and login simply never works.

Fix: `data.strip()`, and validate it as 64 hex characters before accepting it,
rejecting anything else with a clear message. This is cheap and removes a
whole class of "user mysteriously cannot log in" support problems — the same
class as the `principals.db` path mismatch recorded in
`pangalactic.vger/vger_review.md`.

Two smaller problems in the same function:
- the **success** popup is built with `QMessageBox.Warning` (482), so a
  successful capture is announced with a warning icon;
- `self.project_file_path = ''` (460) sets an attribute that has nothing to do
  with keys — evidently copy-pasted from a file-import dialog.

**STATUS: FIXED.** `on_get_key` now `strip()`s the file contents and validates
them with a new module-level `valid_public_key()` (64 hex characters). The
read uses `with`, the stray `project_file_path` assignment is gone, and the
success popup is now `QMessageBox.Information`.

*Precision about what the fix does, since an earlier draft of this entry said
it "rejects anything else":* for the **trailing-newline case — the one that
actually occurs — it repairs rather than rejects.** `strip()` yields the clean
64-character key and the file is accepted. Rejection is reserved for genuinely
malformed content (wrong length, non-hex), where a message naming the actual
length is the most useful thing to say. Repairing the common case is the
better behaviour: an administrator handed a key by email should not have to
know that an invisible character is why their colleague cannot log in.

**Verified by execution** across the accept/reject cases:

| input | accepted |
|---|---|
| clean 64-char hex | yes |
| **trailing newline** | **no** (was silently accepted) |
| trailing space | no |
| uppercase hex | yes |
| too short / too long / non-hex / empty / `None` / bytes | no |

and `strip()` rescues the newline case, which is the one that actually occurs.

**Confirmed live against marvin (2026-08-01), against the real authenticator
rather than a model of it.** A second test user was registered with a
newline-bearing key exactly as the pre-fix code would have stored it, then the
same key file was put through the fixed dialog:

| step | result |
|---|---|
| register `pinky` with `<key>\n` (pre-fix behaviour) | `add_person -> pk_added=True` — **the server reports complete success** |
| `pinky` attempts to log in | **refused**: `pangalactic.no_such_user [no principal with matching public]` |
| same key file through the **fixed** dialog | stripped to a clean 64-char key |
| re-register and log in | `connected as authid='pinky' role='user'` |

The first two lines are the whole point: **nothing anywhere reports a
problem.** The administrator is told the user was added *with their public
key*, the server logs success, and the failure only ever appears as the new
user being unable to log in, with no diagnostic connecting the two. That is
what made this worth fixing rather than tidying.

Incidentally, the same run confirmed the userid-uniqueness fallback added to
`vger.add_person` (see `pangalactic.vger/vger_review.md`): re-registering
`pinky` matched the existing person by userid and **updated** them, leaving
one `pinky` in the roster rather than two.

### 5. `refresh_roles` silently drops role assignments that share a role and a last name
`admin.py:643-646`

```python
            ra_dict = {
                (ra.assigned_role.name, ra.assigned_to.last_name or '') : ra
                for ra in orb.search_exact(cname='RoleAssignment',
                                           role_assignment_context=self.org)}
```
The dict is keyed by `(role name, last name)`, so two different people with
the same last name holding the same role in the same organization collapse
into one entry and **only the last one is displayed**. **Verified by
execution** — three assignments render as two rows, with one person's
assignment absent:

```
3 role assignments -> 2 rows displayed
shown:   ['bob-smith', 'carol-jones']
MISSING: ['alice-smith']
```

The administrator sees an incomplete picture of who holds what, with no
indication anything is missing — and the missing assignment is still live in
the repository. Two people sharing a surname on one project is not exotic.

Fix: key by `ra.oid` and sort by the tuple, rather than keying by the tuple.

Related, in the same expression: `ra.assigned_role.name` and
`ra.assigned_to.last_name` are dereferenced without a `None` guard, so a
RoleAssignment with a missing role or person raises. There is a defensive
`or ''` on `last_name` but not on the objects themselves.

**STATUS: FIXED.** The dict is replaced by a sorted list, with `ra.oid` in the
sort key so the order is stable even for two people with identical names.
**Verified by execution** on four assignments including two `Smith`s holding
the same role:

| | displayed | missing |
|---|---|---|
| pre-fix | 3 — `['Dave Smith', 'Carol Jones', 'Bob Smith']` | **`Alice Smith`** |
| post-fix | 4 — all of them | none |

The `None` dereference is fixed too, via a new `displayable_ras()` that filters
out RoleAssignments missing `assigned_to` or `assigned_role` and logs each one
skipped. It is applied to the global-admin list as well as the per-org list.
Verified: 3 records in (one sound, one with no role, one with no person) → 1
displayable. This matters more than it looks — `get_labels()` would have
raised on the corrupt record and taken the **entire** role-assignment panel
with it, so one bad row could hide every good one.

### 6. The "TBD" duplicate check is not scoped to the organization
`admin.py:821-825`

```python
                ra_tbd = orb.search_exact(cname='RoleAssignment',
                                          assigned_role=role,
                                          assigned_to=tbd)
                if ra_tbd:
                    orb.log.info('        already have TBD -- ignoring.')
```
The search omits `role_assignment_context=self.org`, so it matches a TBD
placeholder for that role in **any** organization. Dropping a Role onto
project B is therefore silently ignored if project A already has a TBD for
it — the administrator gets no feedback at all (an `info` log line), and the
role never appears. Add `role_assignment_context=self.org` to the search.

**STATUS: FIXED.** The search is now scoped with
`role_assignment_context=self.org`. **Verified by execution** against a store
holding a TBD "SE" in ProjectA:

| drop | pre-fix | post-fix |
|---|---|---|
| "SE" onto **ProjectB** | **ignored** (wrong) | added |
| "SE" onto **ProjectA** | ignored | ignored (correct) |

The silent half is fixed too: when the drop *is* correctly ignored the
administrator now gets a short notice naming the organization and the role,
rather than the drop appearing to do nothing at all.

### 7. `AddPersonDialog` will crash if opened without going through the search dialog first
`admin.py:414-421`

```python
        self.schema = config.get('ldap_schema')
        self.form_widgets = {}
        for name in self.schema:
```
`schema` is `None` when `ldap_schema` is not configured, and iterating it
raises `TypeError`. Today this is unreachable because `PersonSearchDialog`
defensively populates `config['ldap_schema']` (257-267) before
`AddPersonDialog` can ever be opened. **It becomes live the moment a direct
"New User" path is added (#2)** — which is why it is worth fixing in the same
change.

More fundamentally, the dialog builds its fields from the *LDAP* schema even
though what it is really editing is a `Person`. A non-LDAP creation path wants
its own field list, mapped to `Person` attributes directly.

**STATUS: FIXED, with #2.** `AddPersonDialog` no longer reads `ldap_schema` at
all — its fields come from the module-level `PERSON_FIELDS`. Verified by
constructing it blank with `ldap_schema` absent from config, which is exactly
the case that used to raise `TypeError`.

## Smaller items

- **`RADropLabel.__init__` discards its `parent` argument** (45-64): it
  accepts `parent=None` and then passes the literal `parent=None` to `super()`,
  so a caller-supplied parent is silently dropped. Same dead-parameter shape as
  `get_next_ref_des`'s `prefix` in the core review.
- **`delete_role` has no confirmation** (85-93). It is a context-menu item
  that immediately deletes a permission record; compare `delete_project`,
  which asks "are you really really sure?". Given #1, it currently deletes
  locally and diverges from the repository, which makes an accidental click
  harder to notice.
- **`RADropLabel.dropEvent`'s two branches are ~90% duplicated** (143-184 vs
  185-226) — identical apart from which of role/person comes from the drop and
  which from the existing assignment. Both would need the #1 fix applied
  separately, which is exactly the hazard duplication creates.
- **Two notification mechanisms for the same operation**: `AdminDialog.dropEvent`
  uses `self.new_object.emit(ra.oid)` in the Person branch (808, with the
  dispatcher call commented out just above it) and
  `dispatcher.send(signal='new object', obj=ra)` in the Role branch (842).
  This is the pydispatcher/pyqtSignal migration the author has flagged as in
  progress; worth converging here since #1 turns on exactly this distinction.
- **The module's own `__main__` block is broken** (852-857): `AdminDialog()`
  with no `org` reaches `ButtonLabel(self.org.id, w=120)` at 544 and raises
  `AttributeError`. `refresh_roles` uses `getattr(self.org, 'id', ...)`
  defensively, so the inconsistency is visible within the class.
- **`if role and not self.org.oid == 'pgefobjects:PGANA'`** (817): when the
  org *is* PGANA the else branch logs "Undefined Role dropped", which
  misdescribes the situation — the role was fine, it just is not allowed in
  that context.

## Status summary

**Fixed** (2026-08-01), each verified by execution and annotated inline:

- **#1** role-assignment deletions now reach `vger.delete`, for both the
  context-menu delete and the drag-drop re-assignment.
- **#4** the public key is stripped and validated before it is accepted.
- **#3** the `ldap_search_button` connect is guarded, so the admin tool opens
  on deployments that do not configure LDAP.

- **#2 + #7** a "New User" button gives a non-LDAP path to creating a user,
  and `AddPersonDialog` no longer depends on `ldap_schema`; `on_save`
  validates required fields, user-id uniqueness, and confirms explicitly when
  no public key has been supplied.

- **#5** `refresh_roles` no longer collapses two people who share a last name
  and a role, and corrupt RoleAssignments are skipped instead of taking the
  whole panel down.
- **#6** the TBD duplicate check is scoped to the organization, and an
  ignored drop now says so.

**All findings in this pass are now fixed.** Remaining are the smaller items
below — most usefully, converging the two notification mechanisms, which
would also remove the double `refresh_roles` noted under #1.

## Suggested fix order

1. **#1 role-assignment deletions** — permissions silently not revoked, and
   drag-drop re-assignment leaves the old assignment live in the repository.
   Nothing else here comes close in consequence.
2. **#4 strip and validate the public key** — a few lines, removes a silent
   login failure that is easy to hit and very hard to diagnose.
3. **#3 guard the `ldap_search_button` connect** — one line, and it is a
   crash-on-open for any deployment that does not set `ldap_schema`.
4. **#2 + #7 the "New User" path** — the actual feature work, and the reason
   this pass happened. #7 must be fixed with it or the new path crashes.
5. **#5 the `ra_dict` key** — one line, and the admin tool currently misleads
   about who holds what.
6. **#6 scope the TBD check**, then the smaller items as convenient.
