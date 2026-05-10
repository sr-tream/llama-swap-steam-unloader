// KWin Script: Steam Unloader (JS-only, KWin 6+)
// Calls org.sr.SteamUnloader.Unload() over D-Bus when a Steam game window appears.
// Pure-JS form is used because declarativescript plugins can't be live-reloaded
// in KWin 6.6.x — see KDE bug 514131.

var DBUS_SERVICE   = "org.sr.SteamUnloader";
var DBUS_PATH      = "/org/sr/SteamUnloader";
var DBUS_INTERFACE = "org.sr.SteamUnloader";
var STEAM_PREFIX   = "steam_app_";

var seen = {};
var unloadPending = false;

function dlog(msg) {
    var s = "steam-unloader: " + msg;
    console.info(s);
    callDBus(DBUS_SERVICE, DBUS_PATH, DBUS_INTERFACE, "Debug", String(s));
}

function isSteam(win) {
    if (!win) return false;
    var cls = win.resourceClass || "";
    return String(cls).indexOf(STEAM_PREFIX) === 0;
}

function triggerUnload(reason) {
    dlog(reason + " — calling Unload()");
    callDBus(DBUS_SERVICE, DBUS_PATH, DBUS_INTERFACE, "Unload");
}

function noteSteam(win, reason) {
    var id = String(win.internalId);
    if (seen[id]) return;
    seen[id] = true;
    if (!unloadPending) {
        unloadPending = true;
        triggerUnload(reason + " " + win.resourceClass);
    }
}

function scanExisting() {
    var list = workspace.windowList();
    for (var i = 0; i < list.length; i++) {
        if (isSteam(list[i])) noteSteam(list[i], "scan");
    }
}

workspace.windowAdded.connect(function(win) {
    if (isSteam(win)) noteSteam(win, "windowAdded");
});

workspace.windowRemoved.connect(function(win) {
    if (!win) return;
    var id = String(win.internalId);
    if (seen[id]) {
        delete seen[id];
        if (Object.keys(seen).length === 0) unloadPending = false;
    }
});

dlog("script loaded");
scanExisting();
