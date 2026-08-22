// Globals the Frida runtime hands a script, described for Monaco's TypeScript service.
//
// @types/frida-gum already declares Interceptor / Memory / Process / Module /
// send / recv / rpc / ptr / hexdump and friends as ambient globals, so they need
// nothing here. Two gaps have to be filled by hand:
//
//   1. The Java bridge ships as an ambient *module* ("frida-java-bridge"), but
//      Friga prepends the compiled bridge to every script so it lands as a plain
//      global `Java` (see core/frida_manager.run_script). Re-expose it as one.
//   2. We deliberately load Monaco without the DOM lib — these scripts run inside
//      an Android process, not a browser, so `document`/`window` completions would
//      be actively misleading. That means `console` has to be declared explicitly.

import Java_ from "frida-java-bridge";

declare global {
    /**
     * The Frida Java bridge. Available because Friga prepends the bundled bridge
     * to the script before loading it — untick "Inject Java bridge" and this will
     * be undefined at runtime.
     */
    const Java: typeof Java_;

    /**
     * Frida's console. Output is routed to Friga's Output Console panel.
     */
    const console: {
        log(...args: any[]): void;
        warn(...args: any[]): void;
        error(...args: any[]): void;
        debug(...args: any[]): void;
        info(...args: any[]): void;
        count(label?: string): void;
    };
}
