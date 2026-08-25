""" Friga theming — a registry of palettes with live switching.

The look is the soft-dark app-launcher one (Steam / Epic): layered surfaces,
rounded corners, a left nav rail, cards, and one accent carrying the emphasis.
Several palettes ship; Crimson (red team) is the default.

How live switching works without editing every panel: geometry and fonts are
theme-independent module constants, but the *colour* names (FG, ACCENT, SUCCESS…)
are served through the module-level __getattr__ below, which forwards to the
current Theme. So a panel that reads ``theme.SUCCESS`` at call time always gets
the active theme's value. Widgets that *bake* a colour in (qtawesome icons, the
console's HTML, device-status cells, the Monaco editor) can't be served that way —
they listen to ``theme.bus.changed`` and repaint.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from PyQt6.QtCore import QObject, pyqtSignal
from string import Template

from core.log_manager import LogLevel

# --- theme-independent geometry & type --------------------------------------
RADIUS_SM = "6px"
RADIUS_MD = "10px"
RADIUS_LG = "14px"
RADIUS_PILL = "999px"
WINDOW_RADIUS = 14

UI_FONT = "Inter"
MONO_FONT = "JetBrains Mono"
UI_FONT_STACK = '"Inter", "Segoe UI", "Ubuntu", sans-serif'
MONO_FONT_STACK = '"JetBrains Mono", "Cascadia Mono", "Consolas", monospace'


def _rgba(hex_colour: str, alpha: float) -> str:
    h = hex_colour.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r}, {g}, {b}, {alpha})"


@dataclass(frozen=True)
class Theme:
    name: str
    is_dark: bool
    bg: str
    bg_sunken: str
    surface: str
    surface_raised: str
    surface_hover: str
    border: str
    border_strong: str
    fg: str
    fg_muted: str
    fg_faint: str
    accent: str
    accent_hover: str
    accent_pressed: str
    on_accent: str
    label_key: str
    success: str
    warning: str
    error: str

    # Upper-case aliases so panels can read theme.FG, theme.ACCENT, … via the
    # module __getattr__ (which forwards to the current Theme instance).
    @property
    def BG(self) -> str: return self.bg
    @property
    def BG_SUNKEN(self) -> str: return self.bg_sunken
    @property
    def SURFACE(self) -> str: return self.surface
    @property
    def SURFACE_RAISED(self) -> str: return self.surface_raised
    @property
    def SURFACE_HOVER(self) -> str: return self.surface_hover
    @property
    def BORDER(self) -> str: return self.border
    @property
    def BORDER_STRONG(self) -> str: return self.border_strong
    @property
    def FG(self) -> str: return self.fg
    @property
    def FG_MUTED(self) -> str: return self.fg_muted
    @property
    def FG_FAINT(self) -> str: return self.fg_faint
    @property
    def ACCENT(self) -> str: return self.accent
    @property
    def ACCENT_HOVER(self) -> str: return self.accent_hover
    @property
    def ACCENT_PRESSED(self) -> str: return self.accent_pressed
    @property
    def ON_ACCENT(self) -> str: return self.on_accent
    @property
    def LABEL_KEY(self) -> str: return self.label_key
    @property
    def SUCCESS(self) -> str: return self.success
    @property
    def WARNING(self) -> str: return self.warning
    @property
    def ERROR(self) -> str: return self.error
    @property
    def INFO(self) -> str: return self.fg
    @property
    def ACCENT_SUBTLE(self) -> str: return _rgba(self.accent, 0.14)
    @property
    def ACCENT_SOFT(self) -> str: return _rgba(self.accent, 0.28)

    def tokens(self) -> dict[str, str]:
        return {
            "BG": self.bg, "BG_SUNKEN": self.bg_sunken, "SURFACE": self.surface,
            "SURFACE_RAISED": self.surface_raised, "SURFACE_HOVER": self.surface_hover,
            "BORDER": self.border, "BORDER_STRONG": self.border_strong,
            "FG": self.fg, "FG_MUTED": self.fg_muted, "FG_FAINT": self.fg_faint,
            "ACCENT": self.accent, "ACCENT_HOVER": self.accent_hover,
            "ACCENT_PRESSED": self.accent_pressed, "ON_ACCENT": self.on_accent,
            "ACCENT_SUBTLE": self.ACCENT_SUBTLE, "ACCENT_SOFT": self.ACCENT_SOFT,
            "LABEL_KEY": self.label_key, "SUCCESS": self.success,
            "WARNING": self.warning, "ERROR": self.error,
            "R_SM": RADIUS_SM, "R_MD": RADIUS_MD, "R_LG": RADIUS_LG,
            "R_PILL": RADIUS_PILL, "UI_FONT": UI_FONT_STACK, "MONO_FONT": MONO_FONT_STACK,
        }

    def console_colours(self) -> dict[LogLevel, str]:
        return {
            LogLevel.SUCCESS: self.success,
            LogLevel.ERROR: self.error,
            LogLevel.WARNING: self.warning,
            LogLevel.INFO: self.fg,
        }

    def monaco_colours(self) -> dict[str, str]:
        # The subset friga-editor.js needs to build a matching Monaco theme.
        return {
            "base": "vs-dark" if self.is_dark else "vs",
            "bg": self.bg_sunken, "fg": self.fg, "faint": self.fg_faint,
            "lineHighlight": self.surface_hover, "selection": self.ACCENT_SOFT,
            "accent": self.accent, "widgetBg": self.surface_raised,
            "border": self.border, "muted": self.fg_muted,
        }


# --- the palettes -----------------------------------------------------------
THEMES: dict[str, Theme] = {
    "Crimson": Theme(
        name="Crimson", is_dark=True,
        bg="#0E0F13", bg_sunken="#0B0C0F", surface="#171A21",
        surface_raised="#1F232C", surface_hover="#262B35",
        border="#2A2E38", border_strong="#363B47",
        fg="#E6E8EC", fg_muted="#9AA0AC", fg_faint="#5B616E",
        accent="#E5484D", accent_hover="#F0595E", accent_pressed="#C93A3F",
        on_accent="#FFFFFF", label_key="#C6CBD4",
        success="#3DD68C", warning="#E5A54B", error="#FF6166",
    ),
    "Blue Team": Theme(
        name="Blue Team", is_dark=True,
        bg="#0E0F13", bg_sunken="#0B0C0F", surface="#171A21",
        surface_raised="#1F232C", surface_hover="#262B35",
        border="#2A2E38", border_strong="#363B47",
        fg="#E6E8EC", fg_muted="#9AA0AC", fg_faint="#5B616E",
        accent="#3B82F6", accent_hover="#5A97F8", accent_pressed="#2E6AD1",
        on_accent="#FFFFFF", label_key="#C6CBD4",
        success="#3DD68C", warning="#E5A54B", error="#FF6166",
    ),
    "Matrix": Theme(
        name="Matrix", is_dark=True,
        bg="#080A08", bg_sunken="#050605", surface="#0E120E",
        surface_raised="#141A14", surface_hover="#1A221A",
        border="#1E281E", border_strong="#2A362A",
        fg="#B9F5C4", fg_muted="#6FBF83", fg_faint="#3E6E4A",
        accent="#34D058", accent_hover="#46E06A", accent_pressed="#28A847",
        on_accent="#041007", label_key="#8FE0A0",
        success="#34D058", warning="#E5C84B", error="#FF5555",
    ),
    "Nord": Theme(
        name="Nord", is_dark=True,
        bg="#2E3440", bg_sunken="#272B35", surface="#3B4252",
        surface_raised="#434C5E", surface_hover="#4C566A",
        border="#434C5E", border_strong="#4C566A",
        fg="#ECEFF4", fg_muted="#9AA3B2", fg_faint="#6B7488",
        accent="#88C0D0", accent_hover="#8FBCBB", accent_pressed="#5E81AC",
        on_accent="#2E3440", label_key="#D8DEE9",
        success="#A3BE8C", warning="#EBCB8B", error="#BF616A",
    ),
    "Dracula": Theme(
        name="Dracula", is_dark=True,
        bg="#282A36", bg_sunken="#21222C", surface="#343746",
        surface_raised="#3C3F51", surface_hover="#44475A",
        border="#3C3F51", border_strong="#565A72",
        fg="#F8F8F2", fg_muted="#A9ADC4", fg_faint="#6272A4",
        accent="#BD93F9", accent_hover="#CBA6FA", accent_pressed="#A579E8",
        on_accent="#21222C", label_key="#C7CBE6",
        success="#50FA7B", warning="#F1FA8C", error="#FF5555",
    ),
    "Daybreak": Theme(
        name="Daybreak", is_dark=False,
        bg="#EDEEF1", bg_sunken="#FFFFFF", surface="#FFFFFF",
        surface_raised="#F4F5F7", surface_hover="#E9EBEF",
        border="#DADCE2", border_strong="#C2C6CF",
        fg="#1A1D23", fg_muted="#5B616E", fg_faint="#9AA0AC",
        accent="#E5484D", accent_hover="#F0595E", accent_pressed="#C93A3F",
        on_accent="#FFFFFF", label_key="#3A3F4A",
        success="#1F9E5F", warning="#B8791F", error="#D93A40",
    ),
}

DEFAULT = "Crimson"


# --- runtime state ----------------------------------------------------------
class _ThemeBus(QObject):
    changed = pyqtSignal(str)   # emits the new theme name


bus = _ThemeBus()
_current = THEMES[DEFAULT]


def current() -> Theme:
    return _current


def names() -> list[str]:
    return list(THEMES)


def console_colours() -> dict[LogLevel, str]:
    return _current.console_colours()


def monaco_colours() -> dict[str, str]:
    return _current.monaco_colours()


def build_qss(theme: Theme | None = None) -> str:
    return _QSS_TEMPLATE.substitute((theme or _current).tokens())


def apply(app, name: str) -> None:
    """Switch the active theme, restyle the app, persist the choice and notify."""
    global _current
    _current = THEMES.get(name, THEMES[DEFAULT])
    app.setStyleSheet(build_qss(_current))
    try:
        from PyQt6.QtCore import QSettings
        QSettings().setValue("ui/theme", _current.name)
    except Exception:
        pass
    bus.changed.emit(_current.name)


def saved_name() -> str:
    try:
        from PyQt6.QtCore import QSettings
        value = QSettings().value("ui/theme")
        if isinstance(value, str) and value in THEMES:
            return value
    except Exception:
        pass
    return DEFAULT


def __getattr__(name: str):
    # Serve colour tokens (theme.FG, theme.ACCENT, …) from the current theme so
    # call-time reads follow the active palette. Real module attributes never
    # reach here.
    if name == "CONSOLE_COLOURS":
        return _current.console_colours()
    try:
        return getattr(_current, name)
    except AttributeError:
        raise AttributeError(f"module 'ui.theme' has no attribute {name!r}") from None


_QSS_TEMPLATE = Template("""
* { outline: none; }

QWidget {
    background-color: transparent;
    color: $FG;
    font-family: $UI_FONT;
    font-size: 13px;
}

QWidget#appRoot {
    background-color: $BG;
    border-radius: ${R_LG};
    border: 1px solid $BORDER;
}

/* Title bar --------------------------------------------------------------- */
QWidget#titleBar { background-color: transparent; }
QLabel#appTitle { color: $FG; font-size: 13px; font-weight: 600; }
QLabel#appMark { color: $ACCENT; font-size: 15px; font-weight: 800; }
QToolButton#winBtn, QToolButton#winClose {
    background: transparent; border: none; border-radius: $R_SM; padding: 6px;
}
QToolButton#winBtn:hover { background-color: $SURFACE_HOVER; }
QToolButton#winClose:hover { background-color: $ACCENT; }

/* Nav rail ---------------------------------------------------------------- */
QWidget#navRail { background-color: $SURFACE; border-right: 1px solid $BORDER; }
QToolButton#navItem {
    background: transparent; color: $FG_MUTED; border: none;
    border-left: 3px solid transparent; border-radius: 0;
    padding: 10px 14px; text-align: left; font-size: 13px; font-weight: 500;
}
QToolButton#navItem:hover { background-color: $SURFACE_HOVER; color: $FG; }
QToolButton#navItem:checked {
    background-color: $ACCENT_SUBTLE; color: $ACCENT;
    border-left: 3px solid $ACCENT; font-weight: 600;
}

/* Cards & group boxes ----------------------------------------------------- */
QFrame#card {
    background-color: $SURFACE; border: 1px solid $BORDER; border-radius: $R_LG;
}
QLabel#cardTitle { color: $FG; font-size: 14px; font-weight: 700; }
QLabel#cardSub { color: $FG_MUTED; font-size: 12px; }
QLabel#pageTitle { color: $FG; font-size: 20px; font-weight: 800; }

QGroupBox {
    background-color: $SURFACE; border: 1px solid $BORDER; border-radius: $R_MD;
    margin-top: 12px; padding: 10px; font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin; subcontrol-position: top left;
    left: 10px; padding: 0 4px; color: $LABEL_KEY;
}

/* Buttons ----------------------------------------------------------------- */
QPushButton {
    background-color: $ACCENT; color: $ON_ACCENT; border: none;
    border-radius: $R_MD; padding: 8px 16px; font-weight: 600;
}
QPushButton:hover { background-color: $ACCENT_HOVER; }
QPushButton:pressed { background-color: $ACCENT_PRESSED; }
QPushButton:disabled { background-color: $SURFACE_RAISED; color: $FG_FAINT; }
QPushButton[class="ghost"] {
    background-color: $SURFACE_RAISED; color: $FG; border: 1px solid $BORDER;
}
QPushButton[class="ghost"]:hover { background-color: $SURFACE_HOVER; border-color: $BORDER_STRONG; }
QPushButton[class="ghost"]:pressed { background-color: $SURFACE; }
QPushButton[class="ghost"]:disabled { color: $FG_FAINT; background-color: $SURFACE; }

/* Inputs ------------------------------------------------------------------ */
QLineEdit, QComboBox, QSpinBox {
    background-color: $BG_SUNKEN; color: $FG; border: 1px solid $BORDER;
    border-radius: $R_PILL; padding: 7px 14px; selection-background-color: $ACCENT_SOFT;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus { border: 1px solid $ACCENT; }
QLineEdit:disabled, QComboBox:disabled { color: $FG_FAINT; }
QComboBox::drop-down { border: none; width: 20px; }
QComboBox QAbstractItemView {
    background-color: $SURFACE_RAISED; color: $FG; border: 1px solid $BORDER;
    border-radius: $R_SM; selection-background-color: $ACCENT_SUBTLE; padding: 4px;
}

/* Check boxes ------------------------------------------------------------- */
QCheckBox { spacing: 7px; color: $FG; }
QCheckBox::indicator {
    width: 16px; height: 16px; border: 1px solid $BORDER_STRONG;
    border-radius: $R_SM; background-color: $BG_SUNKEN;
}
QCheckBox::indicator:hover { border-color: $ACCENT; }
QCheckBox::indicator:checked { background-color: $ACCENT; border-color: $ACCENT; }

/* Tables ------------------------------------------------------------------ */
QTableWidget, QTableView {
    background-color: $BG_SUNKEN; alternate-background-color: $SURFACE;
    gridline-color: transparent; selection-background-color: $ACCENT_SUBTLE;
    selection-color: $FG; border: 1px solid $BORDER; border-radius: $R_MD;
}
QTableWidget::item, QTableView::item { padding: 4px 6px; border: none; }
QTableWidget::item:selected, QTableView::item:selected { background-color: $ACCENT_SUBTLE; }
QHeaderView::section {
    background-color: $SURFACE; color: $FG_MUTED; padding: 7px 6px; border: none;
    border-bottom: 1px solid $BORDER; font-weight: 600;
}
QTableCornerButton::section { background-color: $SURFACE; border: none; }

/* Lists ------------------------------------------------------------------- */
QListWidget {
    background-color: $BG_SUNKEN; border: 1px solid $BORDER;
    border-radius: $R_MD; padding: 4px;
}
QListWidget::item { padding: 7px 10px; border-radius: $R_SM; }
QListWidget::item:selected { background-color: $ACCENT_SUBTLE; color: $ACCENT; }
QListWidget::item:hover:!selected { background-color: $SURFACE_HOVER; }

/* Text surfaces ----------------------------------------------------------- */
QTextEdit, QPlainTextEdit {
    background-color: $BG_SUNKEN; color: $FG; border: 1px solid $BORDER;
    border-radius: $R_MD; font-family: $MONO_FONT; selection-background-color: $ACCENT_SOFT;
}

/* Progress bar ------------------------------------------------------------ */
QProgressBar {
    background-color: $BG_SUNKEN; border: 1px solid $BORDER; border-radius: $R_PILL;
    text-align: center; color: $FG; height: 18px;
}
QProgressBar::chunk { background-color: $ACCENT; border-radius: $R_PILL; }

/* Tabs -------------------------------------------------------------------- */
QTabBar::tab {
    background: transparent; color: $FG_MUTED; padding: 7px 14px;
    border: none; border-bottom: 2px solid transparent;
}
QTabBar::tab:selected { color: $FG; border-bottom: 2px solid $ACCENT; }
QTabBar::tab:hover:!selected { color: $FG; }

/* Splitter ---------------------------------------------------------------- */
QSplitter::handle { background-color: transparent; }
QSplitter::handle:hover { background-color: $ACCENT_SOFT; }
QSplitter::handle:horizontal { width: 6px; }
QSplitter::handle:vertical { height: 6px; }

/* Scrollbars -------------------------------------------------------------- */
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
    background: $BORDER_STRONG; border-radius: 5px; min-height: 28px; min-width: 28px;
}
QScrollBar::handle:hover { background: $FG_FAINT; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }

/* Status strip & tooltips ------------------------------------------------- */
QWidget#statusStrip { background-color: $SURFACE; border-top: 1px solid $BORDER; }
QLabel#statusItem { color: $FG_MUTED; font-size: 12px; }
QLabel#statusKey { color: $FG_FAINT; font-size: 12px; }
QToolTip {
    background-color: $SURFACE_RAISED; color: $FG; border: 1px solid $BORDER;
    border-radius: $R_SM; padding: 5px 8px;
}

/* Menus ------------------------------------------------------------------- */
QMenu { background-color: $SURFACE_RAISED; color: $FG; border: 1px solid $BORDER; border-radius: $R_SM; }
QMenu::item { padding: 6px 24px; border-radius: $R_SM; }
QMenu::item:selected { background-color: $ACCENT_SUBTLE; }
QMenu::separator { height: 1px; background: $BORDER; margin: 4px 8px; }
""")

# Back-compat: the default stylesheet, for callers that want a static one.
DARK_QSS = build_qss(THEMES[DEFAULT])
