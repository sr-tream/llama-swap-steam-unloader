// KWin Script: Steam Unloader (JS-only, KWin 6+)
// Calls org.sr.SteamUnloader.Unload() over D-Bus when a configured game window appears.
// Pure-JS form is used because declarativescript plugins can't be live-reloaded
// in KWin 6.6.x — see KDE bug 514131.

var DBUS_SERVICE   = "org.sr.SteamUnloader";
var DBUS_PATH      = "/org/sr/SteamUnloader";
var DBUS_INTERFACE   = "org.sr.SteamUnloader";
var DEFAULT_CLASS_REGEX = "^steam_app_.*$";

var configuredClassRegex = readConfig("classRegex", DEFAULT_CLASS_REGEX);
if (configuredClassRegex === undefined || configuredClassRegex === null ||
        String(configuredClassRegex).trim() === "") {
    configuredClassRegex = DEFAULT_CLASS_REGEX;
}

var classRegex;
var invalidClassRegex = false;
try {
    classRegex = new RegExp(String(configuredClassRegex));
} catch (error) {
    invalidClassRegex = true;
    classRegex = new RegExp(DEFAULT_CLASS_REGEX);
}

var seen = {};
var unloadPending = false;

function dlog(msg) {
    var s = "steam-unloader: " + msg;
    console.info(s);
    callDBus(DBUS_SERVICE, DBUS_PATH, DBUS_INTERFACE, "Debug", String(s));
}

function isGameWindow(win) {
    if (!win) return false;
    var cls = String(win.resourceClass || "");
    classRegex.lastIndex = 0;
    return classRegex.test(cls);
}

function triggerUnload(reason) {
    dlog(reason + " — calling Unload()");
    callDBus(DBUS_SERVICE, DBUS_PATH, DBUS_INTERFACE, "Unload");
}

function noteGameWindow(win, reason) {
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
        if (isGameWindow(list[i])) noteGameWindow(list[i], "scan");
    }
}

workspace.windowAdded.connect(function(win) {
    if (isGameWindow(win)) noteGameWindow(win, "windowAdded");
});

workspace.windowRemoved.connect(function(win) {
    if (!win) return;
    var id = String(win.internalId);
    if (seen[id]) {
        delete seen[id];
        if (Object.keys(seen).length === 0) unloadPending = false;
    }
});

dlog("script loaded (class regex: " + classRegex.source +
     (invalidClassRegex ? "; invalid configured regex, using default" : "") + ")");
scanExisting();
