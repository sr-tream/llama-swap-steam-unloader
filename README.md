# llama-swap Steam Unloader

Free up your GPU for games automatically. When a Steam game window appears on
KDE Plasma 6, this project tells [llama-swap](https://github.com/mostlygeek/llama-swap)
to unload its currently loaded LLM, so Steam doesn't have to fight your
language model for VRAM.

## How it works

```
┌────────────────────────┐  windowAdded  ┌──────────────────────┐  HTTP POST   ┌─────────────┐
│  KWin script           │ ───────────▶ │  D-Bus daemon        │ ───────────▶│  llama-swap │
│  (steam_app_* match)   │  D-Bus call   │  org.sr.SteamUnloader│   /unload    │             │
└────────────────────────┘               └──────────────────────┘              └─────────────┘
```

1. A small JS-only KWin script watches `workspace.windowAdded` for windows
   whose `resourceClass` starts with `steam_app_`.
2. On match it calls `org.sr.SteamUnloader.Unload()` over the session bus.
3. A user-level systemd service runs a Python daemon that exports that
   D-Bus interface and POSTs to llama-swap's
   [`/api/models/unload`](https://github.com/mostlygeek/llama-swap) endpoint.
4. A 30-second cooldown in the daemon coalesces repeat fires (e.g. from a
   game that opens several windows at launch).

The split exists because KWin scripts are sandboxed and can't speak HTTP — a
tiny D-Bus shim is the simplest bridge.

## Requirements

- KDE Plasma 6 / KWin 6.x (Wayland or X11)
- Python 3.10+ with [`dbus-fast`](https://pypi.org/project/dbus-fast/)
- `curl` on `$PATH`
- A running [llama-swap](https://github.com/mostlygeek/llama-swap) instance
  reachable at `http://localhost:12434` (default — change in
  `dbus-service/steam-unloader-dbus-server.py` if yours lives elsewhere)
- Build deps: `make`, `zip`, `kpackagetool6`, `kwriteconfig6`

## Install

```bash
make install
```

That builds `steam-unloader.kwinscript`, installs the KWin package via
`kpackagetool6`, drops the daemon into `~/.local/bin/`, the systemd unit into
`~/.config/systemd/user/`, and enables both.

After install, **log out and log back in** (or `loginctl terminate-user $USER`)
so KWin loads the script. Verify:

```bash
tail -f ~/.local/state/steam-unloader.log
```

You should see `script loaded` immediately on session start, and
`Unload request received` followed by `Models unloaded successfully` whenever
a Steam game launches.

## Uninstall

```bash
make uninstall
```

## Manual install (no Makefile)

```bash
# KWin script
make package
kpackagetool6 -t KWin/Script -i steam-unloader.kwinscript
kwriteconfig6 --file kwinrc --group Plugins --key steam-unloaderEnabled true

# D-Bus daemon
install -Dm755 dbus-service/steam-unloader-dbus-server.py ~/.local/bin/
install -Dm644 dbus-service/steam-unloader.service        ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now steam-unloader.service
```

You can also install the KWin script through the GUI:
**System Settings → Window Behavior → KWin Scripts → Install From File…**
and pick `steam-unloader.kwinscript`.

## Configuration

All daemon knobs are environment-overridable. Defaults match common setups; set
overrides via `~/.config/systemd/user/steam-unloader.service.d/override.conf`
(use `systemctl --user edit steam-unloader.service` for a guided edit) and add
`Environment=KEY=value` lines under `[Service]`.

| Variable                  | Default                                          | Purpose                                              |
| ------------------------- | ------------------------------------------------ | ---------------------------------------------------- |
| `STEAM_UNLOADER_URL`      | `http://localhost:12434/api/models/unload`       | llama-swap unload endpoint                           |
| `STEAM_UNLOADER_COOLDOWN` | `30` (seconds)                                   | Debounce window for repeat fires                     |
| `STEAM_UNLOADER_API_KEY`  | *(unset)*                                        | Optional bearer token for llama-swap behind auth     |
| `STEAM_UNLOADER_LOG_DIR`  | `$XDG_STATE_HOME` (or `~/.local/state`)          | Where `steam-unloader.log` is written                |

After editing, `systemctl --user restart steam-unloader.service`.

The detection prefix is at the top of `kwin-script/contents/code/main.js`:

```javascript
var STEAM_PREFIX = "steam_app_";
```

Steam games on Linux always set `WM_CLASS = steam_app_<appid>` (both X11 and
Wayland via `xdg-toplevel.set_app_id`), so the prefix match is reliable.

## D-Bus interface

`org.sr.SteamUnloader` at `/org/sr/SteamUnloader`:

| Method            | In   | Out  | Purpose                                                |
| ----------------- | ---- | ---- | ------------------------------------------------------ |
| `Unload()`        |      | `b`  | Unload all loaded models. Honours cooldown.            |
| `Status()`        |      | `s`  | Daemon status string.                                  |
| `Debug(s)`        | msg  | `b`  | Log `msg` to `~/.local/state/steam-unloader.log`.      |

Probe it manually:

```bash
gdbus call --session --dest org.sr.SteamUnloader \
  --object-path /org/sr/SteamUnloader \
  --method org.sr.SteamUnloader.Status
```

## Credits

- [llama-swap](https://github.com/mostlygeek/llama-swap) by mostlygeek — the LLM
  hot-swapper that this project drives.

## License

[MIT](LICENSE)
