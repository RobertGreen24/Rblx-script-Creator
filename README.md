# RobloxForge

A small Flask website for **creating Roblox (Luau) scripts**: tick the features your game needs,
tune the numbers, and it generates complete, commented scripts laid out the way Roblox expects -
plus a `.zip` that works with [Rojo](https://rojo.space) straight away.

![Flask](https://img.shields.io/badge/Flask-3.x-000?logo=flask) ![Python](https://img.shields.io/badge/Python-3.10%2B-3776ab?logo=python) ![No build step](https://img.shields.io/badge/frontend-no%20build%20step-4ade9b)

> Unofficial fan tool. Not affiliated with or endorsed by Roblox Corporation.

---

## What it does

**Feature builder** (`/builder`) - 17 generators across four categories:

| Category | Generators |
| --- | --- |
| Movement | Sprint (with stamina), Double jump (+ mobile button), Dash |
| Player Stats | Leaderstats + DataStore saving, Collectable coins, Passive income, Leaderboard HUD |
| World & Hazards | Kill bricks, Checkpoints, Void rescue, Speed pads, Jump pads, Teleport pads, Day/night cycle |
| Game Systems | Round system (+ HUD), Admin chat commands, Team assigner |

Everything you tick is generated together and cross-wired: pick *Leaderstats + saving* and
*Collectable coins* and the coins pay into a real, saved leaderstat through a shared
`ReplicatedStorage.Shared.StatsAPI` module that is only emitted once.

**Luau editor** (`/editor`) - a zero-dependency editor in the browser: live syntax highlighting
(hand-written tokenizer, no CDN), line numbers, Tab/Shift+Tab indent, Enter keeps indentation,
Ctrl+S to save, starter templates, and a **Luau analyser** that flags the classic footguns
(`:connect()` instead of `:Connect()`, `wait()` instead of `task.wait()`, unguarded DataStore
calls, `game.Players.LocalPlayer` on the server, and more).

**Snippet library** (`/snippets`) - 12 copy/paste patterns: server/client remotes with validation,
DataStores with retries and `BindToClose`, notification toasts, damage numbers, tool melee that
actually damages, countdown timers, weighted loot rolls, animation helpers and more. You can add
and delete your own snippets too.

**My projects** (`/projects`) - every script you save is stored in SQLite with its builder
configuration, so you can reopen, star, edit or delete it later.

### What a download looks like

```
MyGame/
├── ReplicatedStorage/Shared/StatsAPI.luau              -- ModuleScript
├── ServerScriptService/Bootstrap/StatsBootstrap.server.luau
├── ServerScriptService/Features/CoinCollect.server.luau
├── ServerScriptService/World/KillBrick.server.luau
├── StarterPlayer/StarterPlayerScripts/Movement/Sprint.client.luau
├── default.project.json                                -- for `rojo serve`
└── README.md                                           -- setup notes per feature
```

`.server.luau` → `Script`, `.client.luau` → `LocalScript`, files under `ReplicatedStorage/Shared`
→ `ModuleScript`.

---

## Quick start

```bash
git clone https://github.com/RobertGreen24/ProjectX.git
cd ProjectX

python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python run.py                      # then open http://127.0.0.1:5000
```

Environment variables (all optional):

| Variable | Default | Purpose |
| --- | --- | --- |
| `HOST` | `0.0.0.0` | Interface to bind |
| `PORT` | `5000` | Port to serve on |
| `FLASK_DEBUG` | `1` | Set to `0` for production behaviour |
| `PROJECTX_DB` | `instance/robloxforge.db` | Where the SQLite database lives |
| `PROJECTX_SECRET_KEY` | dev value | Flask session secret |

### Production

```bash
pip install waitress
waitress-serve --host 0.0.0.0 --port 5000 run:app
```

### Tests

```bash
python -m unittest discover -s tests -v     # 27 tests, no extra packages needed
```

The suite checks that every generator produces scripts, that the output paths match the script
type, that no template placeholders leak into the Luau, that parameters are clamped and coerced,
and that the project/snippet APIs behave - plus that generated zips are valid and deterministic.

---

## Where the generated code goes

| Service | Contents |
| --- | --- |
| `ServerScriptService` | everything that must be trusted: coins, hazards, rounds, saving, admin commands |
| `StarterPlayer/StarterPlayerScripts` | client-only code: sprint, dash, double jump, HUDs |
| `ReplicatedStorage/Shared` | `StatsAPI` module shared by server and client |

Every generated file starts with a banner telling you where to put it, and the downloaded
`README.md` repeats the setup notes for the features you picked (for example: *tag your parts
`Coin` in the Tag Editor*, or *enable Studio Access to API Services before testing DataStores*).

---

## Project layout

```
ProjectX/
├── run.py                     # dev entry point
├── requirements.txt
├── app/
│   ├── __init__.py            # application factory, Jinja filters
│   ├── db.py                  # SQLite schema, seeding, request-scoped connections
│   ├── snippets.py            # the built-in Luau snippet catalogue
│   ├── features/
│   │   ├── core.py            # Param/Feature/Script types + build pipeline + zip/Rojo output
│   │   ├── catalog.py         # the 17 generators and their Luau templates
│   │   └── __init__.py        # public API of the package
│   ├── routes/
│   │   ├── pages.py           # HTML routes
│   │   └── api.py             # /api JSON endpoints
│   ├── templates/             # Jinja templates (base, builder, editor, snippets, projects)
│   └── static/
│       ├── css/style.css      # hand-written design system, no framework
│       └── js/                # app.js, highlight.js, builder.js, editor.js, snippets.js
└── tests/test_app.py
```

## HTTP API

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/api/features` | Generator catalogue with parameter metadata |
| `POST` | `/api/build` | `{project_name, features:[{id, params}]}` → generated scripts + combined preview |
| `POST` | `/api/download` | Same body → `.zip` (also accepts the config as a form field) |
| `GET/POST` | `/api/projects` | List / save scripts |
| `GET/PATCH/DELETE` | `/api/projects/<id>` | Read, update (including `starred`), delete |
| `GET/POST` | `/api/snippets` | List (supports `?q=` and `?category=`) / add |
| `DELETE` | `/api/snippets/<id>` | Delete your own snippets (built-ins are protected) |

Example:

```bash
curl -X POST http://127.0.0.1:5000/api/build \
  -H 'Content-Type: application/json' \
  -d '{"features":[{"id":"sprint","params":{"sprint_speed":40}},{"id":"coin_collect"}]}'
```

## Adding your own generator

1. Write the Luau as a module-level template in `app/features/catalog.py`, using `${placeholders}`.
2. Write a `_gen_your_feature(params, ctx)` function returning `Script(path, type, code)` objects.
3. Register a `Feature(...)` in `ALL_FEATURES` with typed `Param`s.
4. Add the feature id to `STATS_USERS` if it needs the shared `StatsAPI`.

It then appears in the builder, the API, the zip export and the tests automatically.

## Notes on the generated Luau

* Server scripts never trust the client; world hazards debounce `Touched` so a single physics step
  cannot fire them twice.
* `StatsAPI` caches per player, autosaves on an interval, saves on `PlayerRemoving`, and calls
  `game:BindToClose`. It skips DataStores in Studio so you can test without API access enabled.
* Client scripts only do what must happen on the client (input, camera, HUD).
* `--!nonstrict` is used in the stats module; everything else stays directive-free so you can paste
  it into any codebase.
