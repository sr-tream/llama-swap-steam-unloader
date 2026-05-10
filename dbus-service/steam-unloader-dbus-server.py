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
import subprocess
import sys
from pathlib import Path

# dbus-fast imports
from dbus_fast.aio import MessageBus
from dbus_fast.service import ServiceInterface, dbus_method
from dbus_fast import BusType, NameFlag

# Configuration
UNLOAD_URL = "http://localhost:12434/api/models/unload"
LOG_DIR = Path(__import__("os").environ.get(
    "XDG_STATE_HOME", str(Path.home() / ".local/state")
))
LOG_FILE = LOG_DIR / "steam-unloader.log"

# D-Bus service identity
BUS_NAME = "org.sr.SteamUnloader"
OBJECT_PATH = "/org/sr/SteamUnloader"
INTERFACE_NAME = "org.sr.SteamUnloader"

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stderr),
    ],
)
log = logging.getLogger("steam-unloader-dbus")

# Prevent duplicate unloads within a short window
_last_unload_time: float = 0
_UNLOAD_COOLDOWN = 30  # seconds


class SteamUnloaderInterface(ServiceInterface):
    """D-Bus interface for steam-unloader."""

    def __init__(self, bus: MessageBus) -> None:
        super().__init__(INTERFACE_NAME)
        self._bus = bus

    @dbus_method()
    def Unload(self) -> "b":
        """Trigger model unloading. Called by KWin JS via KWin.callDBus()."""
        global _last_unload_time
        now = asyncio.get_event_loop().time()

        if now - _last_unload_time < _UNLOAD_COOLDOWN:
            log.info("Unload request ignored (cooldown: %.0f/%ds)",
                     now - _last_unload_time, _UNLOAD_COOLDOWN)
            return False

        _last_unload_time = now
        log.info("Unload request received from D-Bus")

        return _trigger_unload()

    @dbus_method()
    def Status(self) -> "s":
        """Return daemon status info."""
        return (f"ok (bus={BUS_NAME}, cooldown={_UNLOAD_COOLDOWN}s, "
                f"last_unload={_last_unload_time:.0f})")

    @dbus_method()
    def Debug(self, msg: "s") -> "b":
        """Debug logging endpoint. Called by KWin JS for logging."""
        log.debug("KWin JS debug: %s", msg)
        return True


def _trigger_unload() -> bool:
    """POST to llama-swap /api/models/unload."""
    try:
        result = subprocess.run(
            ["curl", "-sf", "-X", "POST", UNLOAD_URL],
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
    log.info("Starting Steam Unloader D-Bus server...")

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    # Connect to session bus
    bus = MessageBus(bus_type=BusType.SESSION)
    await bus.connect()
    log.info("Connected to D-Bus session bus (unique: %s)", bus.unique_name)

    # Export our interface
    interface = SteamUnloaderInterface(bus)
    bus.export(OBJECT_PATH, interface)
    log.info("Exported %s at %s", INTERFACE_NAME, OBJECT_PATH)

    # Request bus name (ALLOW_REPLACEMENT: take over if old daemon is running)
    await bus.request_name(BUS_NAME, flags=NameFlag.ALLOW_REPLACEMENT)
    log.info("Acquired bus name %s", BUS_NAME)

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
