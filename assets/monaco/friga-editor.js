// Monaco bootstrap for Friga's script editor.
//
// Talks to the Python side over QWebChannel (the `bridge` object registered by
// ui/editor/monaco_editor.py). Python never reads the editor synchronously — every
// change is pushed here to a mirror on the Python side, which is what
// ScriptEditorPanel.script_text() returns.
//
// Workers are NOT configured here on purpose: vs/editor/editor.main.js installs its
// own self.MonacoEnvironment.getWorker, building each worker from a Blob URL. That
// only works because the page is served over the friga:// scheme with CorsEnabled +
// SecureScheme set — see MonacoScheme in monaco_editor.py. Without the TS worker
// there is no IntelliSense, so if completions ever go missing, suspect the scheme
// flags before suspecting this file.

(function () {
    "use strict";

    var editor = null;
    var bridge = null;
    var suppressChange = false;   // set while we apply text that came *from* Python
    var pushTimer = null;

    // Build a Monaco theme from Friga's palette (colours pushed from ui/theme.py),
    // so the editor tracks whatever app theme is active. `c` is theme.monaco_colours().
    function buildTheme(c) {
        c = c || {};
        var strip = function (x) { return (x || "#000000").replace("#", ""); };
        return {
            base: c.base === "vs" ? "vs" : "vs-dark",
            inherit: true,
            rules: [
                { token: "", foreground: strip(c.fg), background: strip(c.bg) },
                { token: "comment", foreground: strip(c.faint) },
                { token: "keyword", foreground: strip(c.accent) },
                { token: "type", foreground: strip(c.accent) }
            ],
            colors: {
                "editor.background": c.bg || "#0B0C0F",
                "editor.foreground": c.fg || "#E6E8EC",
                "editor.lineHighlightBackground": c.lineHighlight || "#262B35",
                "editor.selectionBackground": c.selection || "#00000040",
                "editorLineNumber.foreground": c.faint || "#5B616E",
                "editorLineNumber.activeForeground": c.fg || "#E6E8EC",
                "editorCursor.foreground": c.fg || "#E6E8EC",
                "editorIndentGuide.background1": c.border || "#2A2E38",
                "editorWidget.background": c.widgetBg || "#1F232C",
                "editorWidget.border": c.border || "#2A2E38",
                "editorSuggestWidget.background": c.widgetBg || "#1F232C",
                "editorSuggestWidget.selectedBackground": c.selection || "#00000040",
                "editorHoverWidget.background": c.widgetBg || "#1F232C",
                "scrollbarSlider.background": (c.border || "#2A2E38") + "aa"
            }
        };
    }

    function applyTheme(monaco, colors) {
        monaco.editor.defineTheme("friga", buildTheme(colors));
        monaco.editor.setTheme("friga");
    }

    function pushText() {
        if (!bridge || !editor) { return; }
        bridge.on_text_changed(editor.getValue());
    }

    function schedulePush() {
        if (suppressChange) { return; }
        if (pushTimer !== null) { clearTimeout(pushTimer); }
        pushTimer = setTimeout(function () {
            pushTimer = null;
            pushText();
        }, 120);
    }

    function configureLanguage(monaco, typings) {
        var js = monaco.languages.typescript.javascriptDefaults;

        js.setCompilerOptions({
            target: monaco.languages.typescript.ScriptTarget.ES2022,
            allowNonTsExtensions: true,
            allowJs: true,
            checkJs: false,          // syntax errors still surface; semantic checks
                                     // would be noise on pasted snippets
            noLib: false,
            // No DOM: these scripts run inside an Android process, so completing
            // document/window/fetch would be actively wrong.
            lib: ["es2022"],
            moduleResolution: monaco.languages.typescript.ModuleResolutionKind.NodeJs
        });

        js.setDiagnosticsOptions({
            noSemanticValidation: true,
            noSyntaxValidation: false
        });

        typings.forEach(function (lib) {
            js.addExtraLib(lib.content, lib.path);
        });
    }

    function attachCommands(monaco) {
        editor.addCommand(monaco.KeyCode.F5, function () {
            pushText();                       // make sure Python has the latest
            if (bridge) { bridge.on_run_requested(); }
        });
        editor.addCommand(
            monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS,
            function () {
                pushText();
                if (bridge) { bridge.on_save_requested(); }
            }
        );
    }

    function init(monaco, initialText, typings, colors) {
        applyTheme(monaco, colors);
        configureLanguage(monaco, typings);

        editor = monaco.editor.create(document.getElementById("root"), {
            value: initialText,
            language: "javascript",
            theme: "friga",
            automaticLayout: true,
            fontFamily: '"JetBrains Mono", "Cascadia Mono", "Consolas", monospace',
            fontSize: 13,
            fontLigatures: true,
            minimap: { enabled: true, renderCharacters: false },
            scrollBeyondLastLine: false,
            renderLineHighlight: "line",
            cursorBlinking: "smooth",
            smoothScrolling: true,
            tabSize: 2,
            insertSpaces: true,
            bracketPairColorization: { enabled: true },
            suggest: { showWords: false },   // prefer the typed Frida API over
                                             // dumb word-based completions
            quickSuggestions: { other: true, comments: false, strings: false },
            padding: { top: 8, bottom: 8 }
        });

        editor.onDidChangeModelContent(schedulePush);
        editor.onDidChangeCursorPosition(function (e) {
            if (bridge) {
                bridge.on_cursor_changed(e.position.lineNumber, e.position.column);
            }
        });

        attachCommands(monaco);

        document.getElementById("boot").classList.add("hidden");
        if (bridge) { bridge.on_ready(); }
    }

    // --- the API Python drives via page().runJavaScript(...) ---
    window.friga = {
        // Live contents. Python's mirror can be a keystroke behind (the push is
        // debounced), so the Run path reads through this instead.
        getText: function () {
            return editor ? editor.getValue() : "";
        },

        setText: function (text) {
            if (!editor) { return; }
            suppressChange = true;
            var model = editor.getModel();
            // pushEditOperations (rather than setValue) keeps the undo stack, so
            // loading a library script is undoable instead of silently destructive.
            model.pushEditOperations(
                [],
                [{ range: model.getFullModelRange(), text: text }],
                function () { return null; }
            );
            editor.setPosition({ lineNumber: 1, column: 1 });
            suppressChange = false;
            pushText();
        },

        resetText: function (text) {
            // Hard reset — used for "New", where losing undo history is intended.
            if (!editor) { return; }
            suppressChange = true;
            editor.setValue(text);
            suppressChange = false;
            pushText();
        },

        setReadOnly: function (flag) {
            if (editor) { editor.updateOptions({ readOnly: !!flag }); }
        },

        setTheme: function (colors) {
            if (window.__monaco) { applyTheme(window.__monaco, colors); }
        },

        focusEditor: function () {
            if (editor) { editor.focus(); }
        },

        insertText: function (text) {
            if (!editor) { return; }
            editor.executeEdits("friga", [{
                range: editor.getSelection(),
                text: text,
                forceMoveMarkers: true
            }]);
            editor.focus();
        },

        // Frida reports script errors with a line number that counts the injected
        // Java bridge, so Python passes an offset to subtract before marking.
        setDiagnostics: function (markers) {
            if (!editor || !window.__monaco) { return; }
            window.__monaco.editor.setModelMarkers(
                editor.getModel(), "frida", markers || []
            );
        },

        clearDiagnostics: function () {
            if (editor && window.__monaco) {
                window.__monaco.editor.setModelMarkers(editor.getModel(), "frida", []);
            }
        },

        revealLine: function (line) {
            if (!editor) { return; }
            editor.revealLineInCenter(line);
            editor.setPosition({ lineNumber: line, column: 1 });
            editor.focus();
        }
    };

    function start() {
        require.config({ paths: { vs: "vs" } });
        require(["vs/editor/editor.main"], function () {
            var monaco = window.monaco;
            window.__monaco = monaco;
            bridge.get_editor_payload(function (raw) {
                var payload = JSON.parse(raw);
                init(monaco, payload.text || "", payload.typings || [], payload.theme);
            });
        });
    }

    new QWebChannel(qt.webChannelTransport, function (channel) {
        bridge = channel.objects.bridge;
        start();
    });
})();
