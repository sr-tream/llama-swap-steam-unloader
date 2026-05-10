#!/usr/bin/env python3
"""Steam Unloader D-Bus Server

Listens on D-Bus session bus for unload requests from KWin JS
and triggers llama-swap model unloading.

Usage:
    steam-unloader-dbus-server.py   # starts the D-Bus server
"""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import sys
from pathlib import Path

# dbus-fast imports
from dbus_fast.aio import MessageBus
from dbus_fast.service import ServiceInterface, dbus_method
from dbus_fast import BusType, NameFlag

# Configuration — overridable via environment, prefixed to avoid collisions.
STEAM_UNLOADER_URL = os.environ.get(
    "STEAM_UNLOADER_URL", "http://localhost:12434/api/models/unload"
)
STEAM_UNLOADER_COOLDOWN = float(os.environ.get("STEAM_UNLOADER_COOLDOWN", "30"))
# Optional bearer token for llama-swap deployments behind auth. Empty = no header.
STEAM_UNLOADER_API_KEY = os.environ.get("STEAM_UNLOADER_API_KEY", "").strip()
STEAM_UNLOADER_LOG_DIR = Path(os.environ.get(
    "STEAM_UNLOADER_LOG_DIR",
    os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state")),
))
STEAM_UNLOADER_LOG_FILE = STEAM_UNLOADER_LOG_DIR / "steam-unloader.log"

# D-Bus service identity
STEAM_UNLOADER_BUS_NAME       = "org.sr.SteamUnloader"
STEAM_UNLOADER_OBJECT_PATH    = "/org/sr/SteamUnloader"
STEAM_UNLOADER_INTERFACE_NAME = "org.sr.SteamUnloader"

STEAM_UNLOADER_LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(STEAM_UNLOADER_LOG_FILE),
        logging.StreamHandler(sys.stderr),
    ],
)
log = logging.getLogger("steam-unloader-dbus")

# Prevent duplicate unloads within a short window
_last_unload_time: float = 0


class SteamUnloaderInterface(ServiceInterface):
    """D-Bus interface for steam-unloader."""

    def __init__(self, bus: MessageBus) -> None:
        super().__init__(STEAM_UNLOADER_INTERFACE_NAME)
        self._bus = bus

    @dbus_method()
    def Unload(self) -> "b":
        """Trigger model unloading. Called by the KWin script via callDBus()."""
        global _last_unload_time
        now = asyncio.get_event_loop().time()

        if now - _last_unload_time < STEAM_UNLOADER_COOLDOWN:
            log.info("Unload request ignored (cooldown: %.0f/%.0fs)",
                     now - _last_unload_time, STEAM_UNLOADER_COOLDOWN)
            return False

        _last_unload_time = now
        log.info("Unload request received from D-Bus")

        return _trigger_unload()

    @dbus_method()
    def Status(self) -> "s":
        """Return daemon status info."""
        return (f"ok (bus={STEAM_UNLOADER_BUS_NAME}, "
                f"cooldown={STEAM_UNLOADER_COOLDOWN:.0f}s, "
                f"last_unload={_last_unload_time:.0f})")

    @dbus_method()
    def Debug(self, msg: "s") -> "b":
        """Debug logging endpoint. Called by the KWin script for logging."""
        log.debug("KWin JS debug: %s", msg)
        return True


def _trigger_unload() -> bool:
    """POST to llama-swap unload endpoint."""
    cmd = ["curl", "-sf", "-X", "POST"]
    if STEAM_UNLOADER_API_KEY:
        cmd += ["-H", f"Authorization: Bearer {STEAM_UNLOADER_API_KEY}"]
    cmd.append(STEAM_UNLOADER_URL)
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            log.info("Models unloaded successfully")
            return True
        else:
            stderr = result.stderr.strip() or "(no stderr)"
            log.warning("Unload failed (curl exit %d): %s",
                        result.returncode, stderr)
            return False
    except subprocess.TimeoutExpired:
        log.error("Unload failed (curl timeout)")
        return False
    except FileNotFoundError:
        log.error("curl not found")
        return False
    except OSError as exc:
        log.error("Unload failed: %s", exc)
        return False


async def main() -> None:
    log.info("Starting Steam Unloader D-Bus server (URL=%s, cooldown=%.0fs)",
             STEAM_UNLOADER_URL, STEAM_UNLOADER_COOLDOWN)

    bus = MessageBus(bus_type=BusType.SESSION)
    await bus.connect()
    log.info("Connected to D-Bus session bus (unique: %s)", bus.unique_name)

    interface = SteamUnloaderInterface(bus)
    bus.export(STEAM_UNLOADER_OBJECT_PATH, interface)
    log.info("Exported %s at %s",
             STEAM_UNLOADER_INTERFACE_NAME, STEAM_UNLOADER_OBJECT_PATH)

    # ALLOW_REPLACEMENT lets a freshly-started daemon take over from an old one.
    await bus.request_name(STEAM_UNLOADER_BUS_NAME,
                           flags=NameFlag.ALLOW_REPLACEMENT)
    log.info("Acquired bus name %s", STEAM_UNLOADER_BUS_NAME)

    log.info("Steam Unloader D-Bus server ready. Waiting for calls...")

    # Run until disconnected
    await bus.wait_for_disconnect()
    log.info("D-Bus server stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Interrupted by user")
    except Exception:
        log.exception("Fatal error")
        sys.exit(1)
