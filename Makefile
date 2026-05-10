# llama-swap Steam Unloader — build/install
#
# Targets:
#   make            — build steam-unloader.kwinscript
#   make install    — install KWin script + D-Bus daemon + systemd unit
#   make uninstall  — remove everything installed by `make install`
#   make clean      — drop built artifacts

PLUGIN_ID    := steam-unloader
KWINSCRIPT   := $(PLUGIN_ID).kwinscript
DBUS_ZIP     := $(PLUGIN_ID)-dbus.zip

PREFIX       ?= $(HOME)/.local
BIN_DIR      := $(PREFIX)/bin
SYSTEMD_DIR  := $(HOME)/.config/systemd/user

DAEMON_SRC   := dbus-service/steam-unloader-dbus-server.py
UNIT_SRC     := dbus-service/steam-unloader.service
DAEMON_NAME  := steam-unloader-dbus-server.py
UNIT_NAME    := steam-unloader.service

KWIN_SOURCES := kwin-script/metadata.json kwin-script/contents/code/main.js
DBUS_SOURCES := $(DAEMON_SRC) $(UNIT_SRC)

.PHONY: all package package-kwin package-dbus install install-kwin install-dbus uninstall clean

all: package

package: package-kwin package-dbus

package-kwin: $(KWINSCRIPT)
package-dbus: $(DBUS_ZIP)

# Build a .kwinscript zip with metadata.json at the archive root, so that
# both `kpackagetool6 -i` and the GUI "Install from File…" KCM accept it.
$(KWINSCRIPT): $(KWIN_SOURCES)
	@command -v zip >/dev/null || { echo "error: 'zip' is required" >&2; exit 1; }
	rm -f $@
	cd kwin-script && zip -r ../$@ metadata.json contents
	@echo "built: $@"

# Build a drop-in zip with home-relative paths so users can `unzip -d ~/`
# straight into place, then enable the systemd unit.
$(DBUS_ZIP): $(DBUS_SOURCES)
	@command -v zip >/dev/null || { echo "error: 'zip' is required" >&2; exit 1; }
	rm -rf .dbus-stage $@
	install -Dm755 $(DAEMON_SRC) .dbus-stage/.local/bin/$(DAEMON_NAME)
	install -Dm644 $(UNIT_SRC)   .dbus-stage/.config/systemd/user/$(UNIT_NAME)
	cd .dbus-stage && zip -r ../$@ .local .config
	rm -rf .dbus-stage
	@echo "built: $@"

install: install-kwin install-dbus

install-kwin: package-kwin
	@command -v kpackagetool6 >/dev/null || { echo "error: 'kpackagetool6' is required" >&2; exit 1; }
	@if kpackagetool6 -t KWin/Script -l 2>/dev/null | grep -qx "$(PLUGIN_ID)"; then \
	    kpackagetool6 -t KWin/Script -u $(KWINSCRIPT); \
	else \
	    kpackagetool6 -t KWin/Script -i $(KWINSCRIPT); \
	fi
	kwriteconfig6 --file kwinrc --group Plugins --key $(PLUGIN_ID)Enabled true
	kwriteconfig6 --file kwinrc --group "Script-$(PLUGIN_ID)" --key Enabled true
	@echo "KWin script installed. Log out / log back in (or restart Plasma) for it to start."

install-dbus:
	install -Dm755 $(DAEMON_SRC) $(BIN_DIR)/$(DAEMON_NAME)
	install -Dm644 $(UNIT_SRC)   $(SYSTEMD_DIR)/$(UNIT_NAME)
	systemctl --user daemon-reload
	systemctl --user enable --now $(UNIT_NAME)
	@echo "D-Bus daemon installed and started."

uninstall:
	-systemctl --user disable --now $(UNIT_NAME)
	-rm -f $(SYSTEMD_DIR)/$(UNIT_NAME)
	-systemctl --user daemon-reload
	-rm -f $(BIN_DIR)/$(DAEMON_NAME)
	-kpackagetool6 -t KWin/Script -r $(PLUGIN_ID)
	-kwriteconfig6 --file kwinrc --group Plugins --key $(PLUGIN_ID)Enabled --delete
	-kwriteconfig6 --file kwinrc --group "Script-$(PLUGIN_ID)" --key Enabled --delete
	@echo "Uninstalled. State files in ~/.local/state/steam-unloader.log are left for inspection."

clean:
	rm -rf $(KWINSCRIPT) $(DBUS_ZIP) .dbus-stage
