"""
ui/theme.py
──────────────────────────────────────────────────────────────────────────────
Hệ thống Design Token & Stylesheet tập trung cho Video Cutter.
Hỗ trợ Dark Mode và Light Mode (tương phản cao).

Tất cả màu sắc, typography và QSS được định nghĩa tại đây.
"""

from pathlib import Path as _Path

# Tính đường dẫn tuyệt đối đến thư mục assets/ (cùng cấp với thư mục ui/)
_ASSETS_DIR = _Path(__file__).parent.parent / "assets"
# Qt QSS dùng forward slash trên mọi nền tảng
_SVG_ARROW_DOWN_URL    = (_ASSETS_DIR / "arrow_down.svg").as_posix()
_SVG_ARROW_DOWN_ON_URL = (_ASSETS_DIR / "arrow_down_on.svg").as_posix()
_SVG_TOGGLE_OFF_URL    = (_ASSETS_DIR / "toggle_off.svg").as_posix()
_SVG_TOGGLE_ON_URL     = (_ASSETS_DIR / "toggle_on.svg").as_posix()

# ═══════════════════════════════════════════════════════════════════════════════
#  COLOUR TOKEN SETS
# ═══════════════════════════════════════════════════════════════════════════════

_DARK_TOKENS = {
    # ── Base backgrounds (High-Contrast Cyberpunk) ──
    "BG_APP":        "#111622",     # Nền đáy — XÁM ĐẬM cao cấp, lớp chìm sâu nhất
    "BG_PANEL":      "#0f1c30",     # Panel NỔI — sáng hơn 1 tông, tách rõ khỏi nền
    "BG_CARD":       "#0f1c30",     # Card bên trong — đồng bộ panel
    "BG_FIELD":      "#080f1e",     # Input/combobox — CHÌM sâu hơn panel
    "BG_CONSOLE":    "#080f1e",     # Log console — chìm sâu
    "BG_TABLE_ALT":  "#0a1525",     # Table alternate row
    # ── Borders ──
    "BORDER_PANEL":  "#ffffff",     # Viền panel — TRẮNG THUẦN, tương phản tuyệt đối
    "BORDER_FIELD":  "#253652",     # Viền input — navy vừa
    "BORDER_FOCUS":  "#3b82f6",     # Focus ring — blue
    # ── Text ──
    "TEXT_PRIMARY":  "#F8FAFC",     # Chữ chính — Off-White
    "TEXT_MUTED":    "#f5f5f5",     # Chữ phụ — trắng gần thuần
    "HEADER_TITLE":  "#F8FAFC",     # Tiêu đề header — sáng
    "HEADER_SUBTITLE": "#94A3B8",   # Phụ đề header — Slate nhạt
    "TEXT_DIM":      "#d0dce8",     # Hint — xám sáng
    "TEXT_BLUE":     "#4a9eff",
    "TEXT_GREEN":    "#10d98c",
    # ── Accents ──
    "ACCENT_BLUE":   "#2563eb",
    "ACCENT_GREEN":  "#059669",
    "ACCENT_RED":    "#dc2626",
    "ACCENT_SWITCH": "#10b981",
    # ── Buttons ──
    "BTN_DEFAULT_BG":       "#182b45",
    "BTN_DEFAULT_BORDER":   "#253d5c",
    "BTN_DEFAULT_HOVER":    "#1e3655",
    "BTN_DEFAULT_HOVER_BD": "#3a5a80",
    "BTN_DEFAULT_PRESSED":  "#101e30",
    "BTN_DEFAULT_DIS_BG":   "#0d1825",
    "BTN_DEFAULT_DIS_BD":   "#182035",
    "BTN_DEFAULT_DIS_FG":   "#3a5270",
    "BTN_NEUTRAL_BG":       "#132030",
    "BTN_NEUTRAL_HOVER":    "#1c2f45",
    "BTN_BROWSE_BG":        "#132030",
    "BTN_BROWSE_HOVER":     "#1c2f45",
    "BTN_OPEN_BG":          "#12202f",
    "BTN_OPEN_HOVER":       "#1c2f45",
    "BTN_OPEN_DIS_FG":      "#2a3f55",
    "BTN_OPEN_DIS_BD":      "#182030",
    "BTN_CLEAR_BG":         "#12202f",
    "BTN_CLEAR_HOVER":      "#1c2f45",
    "BTN_START_DIS_BG":     "#0d2e18",
    "BTN_START_DIS_FG":     "#2d6b42",
    "BTN_CANCEL_DIS_BG":    "#2a0e10",
    "BTN_CANCEL_DIS_FG":    "#5e2428",
    "BTN_ADD_DIS_BG":       "#1a3566",
    "BTN_ADD_DIS_FG":       "#5a7aaa",
    # ── Table ──
    "TABLE_SELECT_BG":      "#1e3a5f",
    "HEADER_BG":            "#2e3b52",     # Table header — XÁM XANH SÁNG, tách biệt hoàn toàn
    "HEADER_SEP":           "#132035",
    # ── ComboBox dropdown ──
    "COMBO_DROPDOWN_BG":    "#0d1c30",
    "COMBO_HOVER_BG":       "#1d6fa8",
    # ── Progress bar ──
    "PROGRESS_BORDER":      "#182840",
    "PROGRESS_BG":          "#0a1525",
    # ── Log console ──
    "LOG_BORDER":           "#ffffff",     # Viền log — trắng đồng bộ panel
    "LOG_TEXT":              "#2ecc9a",
    # ── Scrollbar ──
    "SCROLL_BG":            "#06101c",
    "SCROLL_HANDLE":        "#1a2d45",
    "SCROLL_HOVER":         "#253d5c",
    # ── SummaryChip ──
    "CHIP_BG":              "#0a1525",
    "CHIP_BORDER":          "#182840",
    # ── SmallCombo ──
    "SMALL_COMBO_BG":       "#0d1f38",
    "SMALL_COMBO_BD":       "#1e3a5f",
    "SMALL_COMBO_FG":       "#e2e8f0",
    # ── Scoped card backgrounds ──
    "CARD_INNER_BG":        "#0c1526",
    "CARD_INNER_BD":        "#1e2538",
    "CARD_TRANS_BD":        "#2e3a55",
    "CARD_COMBO_BD":        "#3f4a60",
    "CARD_COMBO_BG":        "#0c1526",
    "CARD_COMBO_HOVER":     "#576785",
    "CARD_COMBO_DIS_BG":    "#0e111a",
    "CARD_COMBO_DIS_FG":    "#3a4255",
    "CARD_COMBO_DIS_BD":    "#1e2538",
    "CARD_DROPDOWN_BG":     "#0c1526",
    "CARD_DROPDOWN_SEL":    "#1a2842",
    "CARD_INPUT_DIS_BG":    "#0e111a",
    "CARD_INPUT_DIS_FG":    "#2d3448",
    "CARD_INPUT_PLACEHOLDER": "#3a4255",
    "CARD_STATUS_FG":       "#8a96b0",
    # ── FeatureCard hover ──
    "FEATURE_HOVER_BG":     "#0e1b30",
    # ── SubPlaceholder ──
    "SUB_PLACEHOLDER_BG":   "#060e1c",
    "SUB_PLACEHOLDER_BD":   "#1a2d45",
    # ── DropZone ──
    "DROPZONE_BD":          "#1a2842",
    # ── SectionTitle ──
    "SECTION_TITLE_FG":     "#ffffff",
    # ── Card label ──
    "CARD_LABEL_FG":        "#ffffff",
}

_LIGHT_TOKENS = {
    # ── Base backgrounds (Card UI: App xám nhạt → Panel trắng tinh) ──
    "BG_APP":        "#f1f5f9",     # Nền app XÁM SÁNG
    "BG_PANEL":      "#ffffff",     # Nền panel TRẮNG TINH — nổi trên nền xám
    "BG_CARD":       "#ffffff",     # Card bên trong — trắng
    "BG_FIELD":      "#f8fafc",     # Input/combobox — xám siêu nhạt
    "BG_CONSOLE":    "#ffffff",     # Log console — trắng
    "BG_TABLE_ALT":  "#f8fafc",     # Table alternate row — xám cực nhạt
    # ── Borders ──
    "BORDER_PANEL":  "#e2e8f0",     # Viền panel — XÁM SIÊU MẢNH, tránh răng cưa bo góc
    "BORDER_FIELD":  "#cbd5e1",     # Viền input — xám mượt mà
    "BORDER_FOCUS":  "#3b82f6",     # Focus ring — blue
    # ── Text ──
    "TEXT_PRIMARY":  "#0f172a",     # Chữ chính — Slate đen đậm
    "TEXT_MUTED":    "#475569",     # Label phụ — xám đậm, dễ đọc
    "HEADER_TITLE":  "#1E293B",     # Tiêu đề header — tối
    "HEADER_SUBTITLE": "#64748B",   # Phụ đề header — Slate dịu mắt
    "TEXT_DIM":      "#64748b",     # Hint text
    "TEXT_BLUE":     "#2563eb",
    "TEXT_GREEN":    "#059669",
    # ── Accents ──
    "ACCENT_BLUE":   "#2563eb",
    "ACCENT_GREEN":  "#059669",
    "ACCENT_RED":    "#dc2626",
    "ACCENT_SWITCH": "#10b981",
    # ── Buttons — GIỮ NGUYÊN solid background, chữ trắng ──
    "BTN_DEFAULT_BG":       "#e2e8f0",
    "BTN_DEFAULT_BORDER":   "#cbd5e1",
    "BTN_DEFAULT_HOVER":    "#cbd5e1",
    "BTN_DEFAULT_HOVER_BD": "#94a3b8",
    "BTN_DEFAULT_PRESSED":  "#94a3b8",
    "BTN_DEFAULT_DIS_BG":   "#f1f5f9",
    "BTN_DEFAULT_DIS_BD":   "#e2e8f0",
    "BTN_DEFAULT_DIS_FG":   "#94a3b8",
    "BTN_NEUTRAL_BG":       "#e2e8f0",
    "BTN_NEUTRAL_HOVER":    "#cbd5e1",
    "BTN_BROWSE_BG":        "#e2e8f0",
    "BTN_BROWSE_HOVER":     "#cbd5e1",
    "BTN_OPEN_BG":          "#cbd5e1",     # "Mở thư mục" — nền cbd5e1, chữ #0f172a
    "BTN_OPEN_HOVER":       "#94a3b8",
    "BTN_OPEN_DIS_FG":      "#94a3b8",
    "BTN_OPEN_DIS_BD":      "#e2e8f0",
    "BTN_CLEAR_BG":         "#e2e8f0",
    "BTN_CLEAR_HOVER":      "#cbd5e1",
    "BTN_START_DIS_BG":     "#bbf7d0",
    "BTN_START_DIS_FG":     "#166534",
    "BTN_CANCEL_DIS_BG":    "#fecaca",
    "BTN_CANCEL_DIS_FG":    "#b91c1c",
    "BTN_ADD_DIS_BG":       "#bfdbfe",
    "BTN_ADD_DIS_FG":       "#1e40af",
    # ── Table ──
    "TABLE_SELECT_BG":      "#bfdbfe",
    "HEADER_BG":            "#f1f5f9",
    "HEADER_SEP":           "#cbd5e1",
    # ── ComboBox dropdown ──
    "COMBO_DROPDOWN_BG":    "#ffffff",
    "COMBO_HOVER_BG":       "#bfdbfe",
    # ── Progress bar ──
    "PROGRESS_BORDER":      "#94a3b8",
    "PROGRESS_BG":          "#e2e8f0",
    # ── Log console ──
    "LOG_BORDER":           "#000000",     # Viền log đồng bộ với viền panel
    "LOG_TEXT":              "#047857",
    # ── Scrollbar ──
    "SCROLL_BG":            "#f1f5f9",
    "SCROLL_HANDLE":        "#94a3b8",
    "SCROLL_HOVER":         "#64748b",
    # ── SummaryChip ──
    "CHIP_BG":              "#e2e8f0",
    "CHIP_BORDER":          "#cbd5e1",
    # ── SmallCombo ──
    "SMALL_COMBO_BG":       "#ffffff",
    "SMALL_COMBO_BD":       "#94a3b8",
    "SMALL_COMBO_FG":       "#0f172a",
    # ── Scoped card backgrounds ──
    "CARD_INNER_BG":        "#ffffff",
    "CARD_INNER_BD":        "#cbd5e1",
    "CARD_TRANS_BD":        "#94a3b8",
    "CARD_COMBO_BD":        "#94a3b8",
    "CARD_COMBO_BG":        "#ffffff",
    "CARD_COMBO_HOVER":     "#64748b",
    "CARD_COMBO_DIS_BG":    "#f1f5f9",
    "CARD_COMBO_DIS_FG":    "#94a3b8",
    "CARD_COMBO_DIS_BD":    "#cbd5e1",
    "CARD_DROPDOWN_BG":     "#ffffff",
    "CARD_DROPDOWN_SEL":    "#e2e8f0",
    "CARD_INPUT_DIS_BG":    "#f1f5f9",
    "CARD_INPUT_DIS_FG":    "#94a3b8",
    "CARD_INPUT_PLACEHOLDER": "#94a3b8",
    "CARD_STATUS_FG":       "#64748b",
    # ── FeatureCard hover ──
    "FEATURE_HOVER_BG":     "#e2e8f0",
    # ── SubPlaceholder ──
    "SUB_PLACEHOLDER_BG":   "#ffffff",
    "SUB_PLACEHOLDER_BD":   "#cbd5e1",
    # ── DropZone ──
    "DROPZONE_BD":          "#94a3b8",
    # ── SectionTitle ──
    "SECTION_TITLE_FG":     "#0f172a",
    # ── Card label ──
    "CARD_LABEL_FG":        "#0f172a",
}


# ═══════════════════════════════════════════════════════════════════════════════
#  STYLESHEET BUILDER
# ═══════════════════════════════════════════════════════════════════════════════


def build_stylesheet(mode: str = "dark") -> str:
    """
    Trả về chuỗi QSS hoàn chỉnh cho ứng dụng.
    mode: "dark" hoặc "light"
    """
    T = _DARK_TOKENS if mode == "dark" else _LIGHT_TOKENS
    hover_bg = "rgba(255, 255, 255, 0.1)" if mode == "dark" else "rgba(0, 0, 0, 0.05)"

    return f"""QWidget {{
    font-family: "Arial";
}}

/* ═══════════════════════════════════════════════════════
   BASE
═══════════════════════════════════════════════════════ */
QMainWindow, QDialog {{
    background-color: {T["BG_APP"]};
}}
QWidget#CentralWidget {{
    background-color: {T["BG_APP"]};
}}
QSplitter {{
    background-color: {T["BG_APP"]};
}}
QSplitter::handle {{
    background-color: {T["BG_APP"]};
}}
QScrollArea {{
    background-color: {T["BG_APP"]};
    border: none;
}}
QScrollArea > QWidget > QWidget {{
    background-color: {T["BG_APP"]};
}}
QWidget {{
    color: {T["TEXT_PRIMARY"]};
    font-family: "Arial";
    font-size: 14px;
    background-color: transparent;
}}

/* ═══════════════════════════════════════════════════════
   SECTION PANELS
═══════════════════════════════════════════════════════ */
QFrame#SectionPanel {{
    background-color: {T["BG_PANEL"]};
    border: 1px solid {T["BORDER_PANEL"]};
    border-radius: 10px;
}}

/* ═══════════════════════════════════════════════════════
   FEATURE CARDS (Processing Row)
═══════════════════════════════════════════════════════ */
QFrame#FeatureCard {{
    background-color: {T["BG_CARD"]};
    border: 1px solid {T["BORDER_PANEL"]};
    border-radius: 8px;
}}
QFrame#FeatureCard:hover {{
    border-color: {T["BORDER_FOCUS"]};
    background-color: {T["FEATURE_HOVER_BG"]};
}}

/* ═══════════════════════════════════════════════════════
   SUBTITLE CONTENT PANEL
═══════════════════════════════════════════════════════ */
QFrame#SubContentPanel {{
    background-color: transparent;
    border: none;
    border-radius: 0px;
    padding: 0px;
}}

/* ═══════════════════════════════════════════════════════
   SUBTITLE SETTINGS CARD
═══════════════════════════════════════════════════════ */
QFrame#subtitle_settings_card {{
    background-color: {T["CARD_INNER_BG"]};
    border: 1px solid {T["CARD_INNER_BD"]};
    border-radius: 6px;
}}

QWidget#LabeledComboContainer {{
    background: transparent;
    border: none;
}}

QFrame#subtitle_settings_card QComboBox {{
    border: 1px solid {T["CARD_COMBO_BD"]};
    border-radius: 5px;
    background-color: {T["CARD_COMBO_BG"]};
    padding: 6px 28px 6px 12px;
    color: {T["TEXT_PRIMARY"]};
    font-size: 14px;
    min-height: 24px;
}}
QFrame#subtitle_settings_card QComboBox:hover {{
    border: 1px solid {T["CARD_COMBO_HOVER"]};
}}
QFrame#subtitle_settings_card QComboBox:focus {{
    border: 1px solid {T["BORDER_FOCUS"]};
}}
QFrame#subtitle_settings_card QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 25px;
    border-left-width: 0px;
    background: transparent;
}}
QFrame#subtitle_settings_card QComboBox::down-arrow {{
    image: url({_SVG_ARROW_DOWN_URL});
    width: 10px;
    height: 6px;
}}
QFrame#subtitle_settings_card QComboBox::down-arrow:on {{
    image: url({_SVG_ARROW_DOWN_ON_URL});
    width: 10px;
    height: 6px;
}}
QFrame#subtitle_settings_card QComboBox QAbstractItemView {{
    border: 1px solid {T["CARD_COMBO_BD"]};
    background-color: {T["CARD_DROPDOWN_BG"]};
    color: {T["TEXT_PRIMARY"]};
    border-radius: 4px;
    padding: 4px;
    margin: 0px;
    outline: none;
    show-decoration-selected: 1;
    selection-background-color: {T["CARD_DROPDOWN_SEL"]};
    selection-color: {T["TEXT_PRIMARY"]};
}}
QFrame#subtitle_settings_card QComboBox QAbstractItemView::item {{
    padding: 6px 10px;
    min-height: 26px;
    border-radius: 3px;
    color: {T["TEXT_PRIMARY"]};
    background-color: transparent;
}}
QFrame#subtitle_settings_card QComboBox QAbstractItemView::item:hover,
QFrame#subtitle_settings_card QComboBox QAbstractItemView::item:selected:hover {{
    background-color: {T["CARD_DROPDOWN_SEL"]};
    color: {T["TEXT_PRIMARY"]};
}}
QFrame#subtitle_settings_card QComboBox QAbstractItemView::item:selected:!hover {{
    background-color: transparent;
    color: {T["TEXT_PRIMARY"]};
}}

/* ═══════════════════════════════════════════════════════
   TRANSLATION SETTINGS CARD
═══════════════════════════════════════════════════════ */
QFrame#translation_settings_card {{
    background-color: {T["CARD_INNER_BG"]};
    border: 1px solid {T["CARD_TRANS_BD"]};
    border-radius: 6px;
}}
QFrame#translation_settings_card QLabel {{
    background: transparent;
    border: none;
    color: {T["CARD_LABEL_FG"]};
}}

QFrame#translation_header_row {{
    background: transparent;
    border: none;
    border-bottom: 1px solid {T["CARD_TRANS_BD"]};
}}

QFrame#TranslationDetailPanel {{
    background: transparent;
    border: none;
}}
QFrame#TranslationDetailPanel QLabel {{
    background: transparent;
    border: none;
    color: {T["CARD_LABEL_FG"]};
}}

QFrame#translation_settings_card QComboBox,
QFrame#TranslationDetailPanel QComboBox {{
    border: 1px solid {T["CARD_COMBO_BD"]};
    border-radius: 5px;
    background-color: {T["CARD_COMBO_BG"]};
    padding: 6px 28px 6px 12px;
    color: {T["TEXT_PRIMARY"]};
    font-size: 14px;
    min-height: 24px;
}}
QFrame#translation_settings_card QComboBox:hover,
QFrame#TranslationDetailPanel QComboBox:hover {{
    border: 1px solid {T["CARD_COMBO_HOVER"]};
}}
QFrame#translation_settings_card QComboBox:focus,
QFrame#TranslationDetailPanel QComboBox:focus {{
    border: 1px solid {T["BORDER_FOCUS"]};
}}
QFrame#translation_settings_card QComboBox:disabled,
QFrame#TranslationDetailPanel QComboBox:disabled {{
    background-color: {T["CARD_COMBO_DIS_BG"]};
    color: {T["CARD_COMBO_DIS_FG"]};
    border-color: {T["CARD_COMBO_DIS_BD"]};
}}
QFrame#translation_settings_card QComboBox::drop-down,
QFrame#TranslationDetailPanel QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 25px;
    border-left-width: 0px;
    background: transparent;
}}
QFrame#translation_settings_card QComboBox::down-arrow,
QFrame#TranslationDetailPanel QComboBox::down-arrow {{
    image: url({_SVG_ARROW_DOWN_URL});
    width: 10px;
    height: 6px;
}}
QFrame#translation_settings_card QComboBox::down-arrow:on,
QFrame#TranslationDetailPanel QComboBox::down-arrow:on {{
    image: url({_SVG_ARROW_DOWN_ON_URL});
    width: 10px;
    height: 6px;
}}
QFrame#translation_settings_card QComboBox QAbstractItemView,
QFrame#TranslationDetailPanel QComboBox QAbstractItemView {{
    border: 1px solid {T["CARD_COMBO_BD"]};
    background-color: {T["CARD_DROPDOWN_BG"]};
    color: {T["TEXT_PRIMARY"]};
    border-radius: 4px;
    padding: 4px;
    margin: 0px;
    outline: none;
    show-decoration-selected: 1;
    selection-background-color: {T["CARD_DROPDOWN_SEL"]};
    selection-color: {T["TEXT_PRIMARY"]};
}}
QFrame#translation_settings_card QComboBox QAbstractItemView::item,
QFrame#TranslationDetailPanel QComboBox QAbstractItemView::item {{
    padding: 6px 10px;
    min-height: 26px;
    border-radius: 3px;
    color: {T["TEXT_PRIMARY"]};
    background-color: transparent;
}}
QFrame#translation_settings_card QComboBox QAbstractItemView::item:hover,
QFrame#translation_settings_card QComboBox QAbstractItemView::item:selected:hover,
QFrame#TranslationDetailPanel QComboBox QAbstractItemView::item:hover,
QFrame#TranslationDetailPanel QComboBox QAbstractItemView::item:selected:hover {{
    background-color: {T["CARD_DROPDOWN_SEL"]};
    color: {T["TEXT_PRIMARY"]};
}}
QFrame#translation_settings_card QComboBox QAbstractItemView::item:selected:!hover,
QFrame#TranslationDetailPanel QComboBox QAbstractItemView::item:selected:!hover {{
    background-color: transparent;
    color: {T["TEXT_PRIMARY"]};
}}

QFrame#translation_settings_card QLineEdit,
QFrame#TranslationDetailPanel QLineEdit {{
    border: 1px solid {T["CARD_COMBO_BD"]};
    border-radius: 5px;
    background-color: {T["CARD_COMBO_BG"]};
    padding: 6px 12px;
    color: {T["TEXT_PRIMARY"]};
    font-size: 13px;
    min-height: 24px;
    letter-spacing: 1px;
}}
QFrame#translation_settings_card QLineEdit:focus,
QFrame#TranslationDetailPanel QLineEdit:focus {{
    border: 1px solid {T["BORDER_FOCUS"]};
}}
QFrame#translation_settings_card QLineEdit:disabled,
QFrame#TranslationDetailPanel QLineEdit:disabled {{
    background-color: {T["CARD_INPUT_DIS_BG"]};
    color: {T["CARD_INPUT_DIS_FG"]};
    border-color: {T["CARD_COMBO_DIS_BD"]};
}}
QFrame#translation_settings_card QLineEdit::placeholder,
QFrame#TranslationDetailPanel QLineEdit::placeholder {{
    color: {T["CARD_INPUT_PLACEHOLDER"]};
}}

QLabel#TranslationFieldLabel {{
    color: {T["CARD_LABEL_FG"]};
    font-size: 12px;
    font-weight: 600;
    background: transparent;
    border: none;
}}
QLabel#TranslationToggleLabel {{
    font-size: 14px;
    font-weight: 700;
    color: {T["CARD_LABEL_FG"]};
    background: transparent;
    border: none;
}}
QLabel#TranslationStatusLabel {{
    font-size: 12px;
    color: {T["CARD_STATUS_FG"]};
    background: transparent;
    border: none;
    font-style: italic;
}}

/* ═══════════════════════════════════════════════════════
   SUBTITLE COLLAPSED PLACEHOLDER
═══════════════════════════════════════════════════════ */
QFrame#SubPlaceholder {{
    background-color: {T["SUB_PLACEHOLDER_BG"]};
    border: 1px dashed {T["SUB_PLACEHOLDER_BD"]};
    border-radius: 6px;
}}

/* ═══════════════════════════════════════════════════════
   DROP ZONE FRAME
═══════════════════════════════════════════════════════ */
QFrame#DropZoneFrame {{
    border: 1px solid {T["DROPZONE_BD"]};
    border-radius: 8px;
    background-color: transparent;
}}

/* ═══════════════════════════════════════════════════════
   TYPOGRAPHY
═══════════════════════════════════════════════════════ */
QLabel#AppTitle {{
    font-size: 16px;
    font-weight: 700;
    color: {T["TEXT_PRIMARY"]};
    background: transparent;
    border: none;
    letter-spacing: 0.3px;
}}
QLabel#SectionTitle {{
    font-weight: 700;
    font-size: 13px;
    color: {T["SECTION_TITLE_FG"]};
    background: transparent;
    border: none;
}}
QLabel#SectionSubtitle {{
    color: {T["TEXT_MUTED"]};
    font-size: 12px;
    background: transparent;
    border: none;
}}
QLabel#CardTitle {{
    font-weight: 700;
    font-size: 14px;
    color: {T["TEXT_PRIMARY"]};
    background: transparent;
    border: none;
}}
QLabel#CardDesc {{
    color: {T["TEXT_MUTED"]};
    font-size: 12px;
    background: transparent;
    border: none;
}}
QLabel#CardSubLabel {{
    color: {T["TEXT_MUTED"]};
    font-size: 12px;
    font-weight: 600;
    background: transparent;
    border: none;
}}
QLabel#FieldLabel {{
    color: {T["TEXT_MUTED"]};
    font-size: 12px;
    font-weight: 600;
    background: transparent;
    border: none;
}}
QLabel#SmoothLabel {{
    color: {T["TEXT_MUTED"]};
    font-size: 12px;
    font-weight: 600;
    background: transparent;
    border: none;
    margin-top: 3px;
}}
QWidget#SmoothContainer {{
    margin-top: 3px;
}}
QLabel#HintLabel {{
    color: {T["TEXT_DIM"]};
    font-size: 12px;
    background: transparent;
    border: none;
}}
QLabel#SubtitleToggleLabel {{
    font-size: 14px;
    font-weight: 600;
    color: {T["TEXT_PRIMARY"]};
    background: transparent;
    border: none;
}}
QLabel#SubPlaceholderLabel {{
    color: {T["TEXT_MUTED"]};
    font-size: 13px;
    background: transparent;
    border: none;
}}
QLabel#SummaryChip {{
    background-color: {T["CHIP_BG"]};
    color: {T["TEXT_MUTED"]};
    padding: 5px 14px;
    border-radius: 6px;
    font-size: 12px;
    font-weight: 600;
    border: 1px solid {T["CHIP_BORDER"]};
}}
QLabel#ProgressLabel {{
    color: {T["TEXT_MUTED"]};
    font-size: 13px;
    background: transparent;
    border: none;
}}
QLabel#ProgressValue {{
    color: {T["TEXT_PRIMARY"]};
    font-size: 13px;
    font-weight: 600;
    background: transparent;
    border: none;
}}
QLabel#ProgressValueGreen {{
    color: {T["TEXT_GREEN"]};
    font-size: 13px;
    font-weight: 700;
    background: transparent;
    border: none;
}}
QLabel#FooterLabel {{
    color: {T["TEXT_DIM"]};
    font-size: 11px;
    background: transparent;
    border: none;
    padding-top: 4px;
    padding-bottom: 4px;
}}

/* ═══════════════════════════════════════════════════════
   INPUTS
═══════════════════════════════════════════════════════ */
QLineEdit, QComboBox {{
    background-color: {T["BG_FIELD"]};
    border: 1px solid {T["BORDER_FIELD"]};
    border-radius: 6px;
    padding: 6px 10px;
    color: {T["TEXT_PRIMARY"]};
    min-height: 24px;
    selection-background-color: {T["ACCENT_BLUE"]};
}}

QLineEdit, QPushButton#btn_browse {{
    height: 32px;
    min-height: 32px;
    max-height: 32px;
}}
QLineEdit {{
    padding: 4px 10px;
}}
QLineEdit:focus {{
    border-color: {T["BORDER_FOCUS"]};
}}

QLineEdit#NumericInput {{
    height: 25px;
    min-height: 25px;
    max-height: 25px;
    padding: 3px 6px;
}}
QComboBox:focus {{
    border-color: {T["BORDER_FOCUS"]};
}}

QComboBox {{
    padding-right: 28px;
}}
QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: center right;
    width: 24px;
    border-left: none;
    background: transparent;
}}
QComboBox::down-arrow {{
    image: url({_SVG_ARROW_DOWN_URL});
    width: 10px;
    height: 6px;
}}
QComboBox::down-arrow:on {{
    image: url({_SVG_ARROW_DOWN_ON_URL});
    width: 10px;
    height: 6px;
}}
QComboBox QAbstractItemView {{
    background-color: {T["COMBO_DROPDOWN_BG"]};
    border: 1px solid {T["BORDER_FIELD"]};
    selection-background-color: transparent;
    selection-color: {T["TEXT_PRIMARY"]};
    color: {T["TEXT_PRIMARY"]};
    outline: none;
    padding: 0px;
    margin: 0px;
    border-radius: 4px;
    show-decoration-selected: 1;
}}
QComboBox QAbstractItemView::item {{
    padding: 6px 30px 6px 10px;
    min-height: 26px;
    border-radius: 4px;
    color: {T["TEXT_PRIMARY"]};
}}
QComboBox QAbstractItemView::item:selected:!hover, QListView::item:selected:!hover {{
    background-color: transparent;
    color: {T["TEXT_PRIMARY"]};
}}
QComboBox QAbstractItemView::item:hover, QListView::item:hover,
QComboBox QAbstractItemView::item:selected:hover, QListView::item:selected:hover {{
    background-color: {T["COMBO_HOVER_BG"]};
    color: #ffffff;
}}
QComboBox#SmallCombo {{
    font-size: 12px;
    min-width: 48px;
    max-width: 48px;
    min-height: 28px;
    padding-left: 4px;
    padding-right: 12px;
}}

/* ═══════════════════════════════════════════════════════
   BUTTONS – DEFAULT
═══════════════════════════════════════════════════════ */
QPushButton {{
    background-color: {T["BTN_DEFAULT_BG"]};
    color: {T["TEXT_PRIMARY"]};
    border: 1px solid {T["BTN_DEFAULT_BORDER"]};
    border-radius: 6px;
    padding: 7px 14px;
    font-weight: 600;
    font-size: 14px;
}}
QPushButton:hover  {{ background-color: {T["BTN_DEFAULT_HOVER"]}; border-color: {T["BTN_DEFAULT_HOVER_BD"]}; }}
QPushButton:pressed {{ background-color: {T["BTN_DEFAULT_PRESSED"]}; }}
QPushButton:disabled {{
    background-color: {T["BTN_DEFAULT_DIS_BG"]};
    border-color: {T["BTN_DEFAULT_DIS_BD"]};
    color: {T["BTN_DEFAULT_DIS_FG"]};
}}

/* ─── Add button (blue) */
QPushButton#btn_add {{
    background-color: #45b6d4;
    color: #ffffff;
    border: none;
    font-weight: bold;
    border-radius: 6px;
}}
QPushButton#btn_add:hover  {{ background-color: #5ec2dc; }}
QPushButton#btn_add:pressed {{ background-color: #319fb9; }}
QPushButton#btn_add:disabled {{ background-color: {T["BTN_ADD_DIS_BG"]}; color: {T["BTN_ADD_DIS_FG"]}; border: none; }}

/* ─── Remove button (red) */
QPushButton#btn_remove {{
    background-color: #bc212a;
    color: #ffffff;
    border: none;
    font-weight: bold;
    border-radius: 6px;
}}
QPushButton#btn_remove:hover  {{ background-color: #d8343e; }}
QPushButton#btn_remove:pressed {{ background-color: #8e1820; }}

/* ─── Neutral small buttons */
QPushButton#btn_neutral {{
    background-color: {T["BTN_NEUTRAL_BG"]};
    color: {T["TEXT_MUTED"]};
    border: 1px solid {T["BTN_DEFAULT_BORDER"]};
    font-size: 13px;
}}
QPushButton#btn_neutral:hover  {{ background-color: {T["BTN_NEUTRAL_HOVER"]}; color: {T["TEXT_PRIMARY"]}; }}



/* ─── Start button (green solid block) */
QPushButton#btn_start {{
    background-color: #2da44e;
    color: #ffffff;
    border: none;
    font-size: 15px;
    font-weight: bold;
    border-radius: 6px;
    padding: 10px;
}}
QPushButton#btn_start:hover {{
    background-color: #34c05a;
    border: none;
}}
QPushButton#btn_start:pressed {{ background-color: #1e7e34; }}
QPushButton#btn_start:disabled {{ background-color: {T["BTN_START_DIS_BG"]}; color: {T["BTN_START_DIS_FG"]}; border: none; }}

/* ─── Cancel button (red solid block — khóa chết cả 2 mode) */
QPushButton#btn_cancel {{
    background-color: #cf222e;
    color: #ffffff;
    border: none;
    font-size: 14px;
    font-weight: bold;
    border-radius: 6px;
    padding: 10px;
}}
QPushButton#btn_cancel:hover {{
    background-color: #e0333e;
    border: none;
}}
QPushButton#btn_cancel:pressed {{ background-color: #8e1820; }}
QPushButton#btn_cancel:disabled {{ background-color: #fecaca; color: #f87171; border: none; }}

/* ─── Open folder button */
QPushButton#btn_open_folder {{
    background-color: {T["BTN_OPEN_BG"]};
    color: {T["TEXT_MUTED"]};
    border: 1px solid {T["BTN_DEFAULT_BORDER"]};
    font-size: 13px;
    border-radius: 6px;
}}
QPushButton#btn_open_folder:hover  {{ background-color: {T["BTN_OPEN_HOVER"]}; color: {T["TEXT_PRIMARY"]}; }}
QPushButton#btn_open_folder:disabled {{ color: {T["BTN_OPEN_DIS_FG"]}; border-color: {T["BTN_OPEN_DIS_BD"]}; }}

/* ─── Clear log button */
QPushButton#btn_clear_log {{
    background-color: {T["BTN_CLEAR_BG"]};
    color: {T["TEXT_MUTED"]};
    border: 1px solid {T["BTN_DEFAULT_BORDER"]};
    border-radius: 6px;
    padding: 4px 12px;
    font-size: 12px;
    font-weight: 500;
}}
QPushButton#btn_clear_log:hover {{ background-color: {T["BTN_CLEAR_HOVER"]}; color: {T["TEXT_PRIMARY"]}; }}

/* Browse button */
QPushButton#btn_browse {{
    background-color: {T["BTN_BROWSE_BG"]};
    color: {T["TEXT_MUTED"]};
    border: 1px solid {T["BTN_DEFAULT_BORDER"]};
    font-size: 13px;
    min-height: 32px;
    max-height: 32px;
    height: 32px;
    padding: 0px 14px;
}}
QPushButton#btn_browse:hover {{ background-color: {T["BTN_BROWSE_HOVER"]}; color: {T["TEXT_PRIMARY"]}; }}

/* ═══════════════════════════════════════════════════════
   TABLE GLOBAL (CONTAINER FRAME ARCHITECTURE)
═══════════════════════════════════════════════════════ */
QFrame#TableContainer {{
    background-color: {T["BG_FIELD"]};
    border: 1px solid {T["BORDER_FIELD"]};
    border-radius: 6px; /* Bo góc cố định lớp ngoài cùng */
}}

QTableWidget {{
    background-color: transparent; /* Trong suốt hoàn toàn để lộ nền bo tròn phía dưới */
    border: none;
    outline: none;
}}
QTableWidget::viewport {{
    background-color: transparent;
}}
QTableWidget::item {{
    padding: 6px 8px;
    background-color: transparent;
    border-bottom: 1px solid {T["HEADER_SEP"]};
    color: {T["TEXT_PRIMARY"]};
}}
QTableWidget::item:selected {{
    background-color: {T["TABLE_SELECT_BG"]};
    color: {T["TEXT_PRIMARY"]};
}}

/* TRÌNH BÀY NHÃN THÔNG BÁO THEO THEME ĐỘNG (ĐÃ TĂNG CỠ CHỮ) */
QLabel#TablePlaceholder {{
    color: {T["TEXT_MUTED"]};
    font-size: 14px; /* Tăng dòng phụ từ 12px lên 13px */
}}
QLabel#TablePlaceholder b {{
    color: {T["TEXT_PRIMARY"]};
    font-size: 16px; /* Tăng dòng tiêu đề đậm từ 13px lên 15px để tạo điểm nhấn */
}}

/* ─── THANH TIÊU ĐỀ HEADER ─── */
QHeaderView {{
    background-color: transparent;
    border: none;
}}
QHeaderView::section {{
    background-color: {T["HEADER_BG"]}; 
    color: {T["TEXT_PRIMARY"]};
    border: none;
    border-right: 1px solid {T["BORDER_FIELD"]}; 
    border-bottom: 2px solid {T["BORDER_FIELD"]};
    padding: 6px 8px;
    font-size: 12px;
    font-weight: 700;
}}
QHeaderView::section:horizontal:first {{
    border-top-left-radius: 5px; /* Khớp góc trên với khung Container */
}}
QHeaderView::section:horizontal:last {{
    border-top-right-radius: 5px;
    border-right: none;
}}

QTableView QTableCornerButton::section {{
    background-color: {T["HEADER_BG"]};
    border: none;
}}

/* ─── THANH CUỘN NỘI BỘ (HẠ THẤP KHỚP KHÍT ĐÁY HEADER) ─── */
QTableWidget QScrollBar:vertical {{
    border: none;
    background: transparent;
    width: 8px;
    margin-top: 39px; 
    margin-bottom: 6px;  
    margin-right: 2px;
}}
QTableWidget QScrollBar::handle:vertical {{
    background: {T["SCROLL_HANDLE"]};
    border-radius: 4px;
    min-height: 20px;
}}
QTableWidget QScrollBar::handle:vertical:hover {{
    background: {T["SCROLL_HOVER"]};
}}
QTableWidget QScrollBar::add-line:vertical, QTableWidget QScrollBar::sub-line:vertical {{
    height: 0;
    background: transparent;
}}
QTableWidget QScrollBar::add-page:vertical, QTableWidget QScrollBar::sub-page:vertical {{
    background: transparent;
}}

/* ═══════════════════════════════════════════════════════
   PROGRESS BAR
═══════════════════════════════════════════════════════ */
QProgressBar {{
    border: 1px solid {T["PROGRESS_BORDER"]};
    border-radius: 5px;
    text-align: center;
    background-color: {T["PROGRESS_BG"]};
    color: {T["TEXT_PRIMARY"]};
    font-weight: 700;
    font-size: 12px;
}}
QProgressBar::chunk {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #059669, stop:1 #10d98c);
    border-radius: 4px;
}}

QTextEdit, QPlainTextEdit {{
    background-color: {T["BG_FIELD"]};
    border: 1px solid {T["BORDER_FIELD"]};
    border-radius: 6px;
    padding: 10px;
    font-family: 'Consolas', 'Cascadia Code', 'Courier New', monospace;
    font-size: 13px;
    color: {T["TEXT_PRIMARY"]};
}}

/* ═══════════════════════════════════════════════════════
   SCROLLBARS
═══════════════════════════════════════════════════════ */
QScrollBar:vertical {{
    border: none;
    background: {T["SCROLL_BG"]};
    width: 8px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {T["SCROLL_HANDLE"]};
    border-radius: 4px;
    min-height: 20px;
}}
QScrollBar::handle:vertical:hover {{ background: {T["SCROLL_HOVER"]}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}

QScrollBar:horizontal {{
    border: none;
    background: {T["SCROLL_BG"]};
    height: 8px;
    margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: {T["SCROLL_HANDLE"]};
    border-radius: 4px;
    min-width: 20px;
}}
QScrollBar::handle:horizontal:hover {{ background: {T["SCROLL_HOVER"]}; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

/* ═══════════════════════════════════════════════════════
   TOGGLE SWITCH (QCheckBox#ToggleSwitch)
═══════════════════════════════════════════════════════ */
QCheckBox#ToggleSwitch {{
    spacing: 0px;
    padding: 0px;
}}
QCheckBox#ToggleSwitch::indicator {{
    width: 44px;
    height: 22px;
    border-radius: 11px;
    image: url({_SVG_TOGGLE_OFF_URL});
}}
QCheckBox#ToggleSwitch::indicator:checked {{
    image: url({_SVG_TOGGLE_ON_URL});
}}
QCheckBox#ToggleSwitch::indicator:disabled {{
    opacity: 0.4;
}}

/* ═══════════════════════════════════════════════════════
   SMALL COMBO (Card 5 platform selector)
═══════════════════════════════════════════════════════ */
QComboBox#SmallCombo {{
    background-color: {T["SMALL_COMBO_BG"]};
    border: 1px solid {T["SMALL_COMBO_BD"]};
    border-radius: 5px;
    color: {T["SMALL_COMBO_FG"]};
    font-size: 12px;
    min-width: 48px;
    max-width: 48px;
    padding-left: 4px;
    padding-right: 12px;
    min-height: 24px;
    max-height: 24px;
}}
QComboBox#SmallCombo::drop-down {{
    border: none;
    width: 18px;
}}
QComboBox#SmallCombo::down-arrow {{
    width: 8px;
    height: 8px;
    image: url({_SVG_ARROW_DOWN_URL});
}}
QComboBox#SmallCombo QAbstractItemView {{
    background-color: {T["SMALL_COMBO_BG"]};
    border: 1px solid {T["SMALL_COMBO_BD"]};
    color: {T["SMALL_COMBO_FG"]};
    font-size: 12px;
    selection-background-color: {T["TABLE_SELECT_BG"]};
}}

QLabel#DurationLabel {{
    font-family: "Arial";
    font-size: 12px;
    font-weight: 600;
    color: {T["TEXT_MUTED"]};
    background: transparent;
    border: none;
    margin-top: 20px;
}}

QLineEdit#DurationInput {{
    height: 25px;
    min-height: 25px;
    max-height: 25px;
    padding: 3px 6px;
    margin-top: 20px;
}}

QWidget#HeaderPanel {{
    background-color: {T["BG_APP"]};
    border-bottom: none;
    padding: 14px 24px;
}}

QLabel#HeaderTitle {{
    font-family: "Arial";
    font-size: 28px;
    font-weight: bold;
    color: {T["HEADER_TITLE"]};
    padding: 0px;
    margin: 0px;
}}

/* Định dạng cho chiếc Tag Premium kế bên tên App */
QLabel#PremiumBadge {{
    background-color: {T["ACCENT_BLUE"]}; /* Hoặc màu Gold/Orange tùy chọn để nổi bật */
    color: #ffffff;
    font-family: "Arial";
    font-size: 10px;
    font-weight: bold;
    padding: 2px 6px;
    border-radius: 4px;
    margin-left: 8px;
}}

QLabel#HeaderSubtitle {{
    font-family: "Arial";
    font-size: 13px;
    font-weight: normal;
    color: {T["HEADER_SUBTITLE"]};
    padding: 0px;
    margin: 0px 0px 2px 0px;
}}

/* Đường gạch chân Gradient — Cam nhạt nhạt dần sang phải */
QFrame#HeaderDivider {{
    border: none;
    min-height: 2px;
    max-height: 2px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #FFD5A1, stop:0.6 rgba(255,213,161,0.3), stop:1 transparent);
    margin-top: 4px;
    margin-bottom: 0px;
}}

QComboBox#HeaderLangMenu {{
    border: 1px solid {T["BORDER_FIELD"]};
    border-radius: 6px;
    padding: 2px 6px;
    height: 26px;
    min-width: 55px;
    background-color: {T["BG_FIELD"]};
}}

QPushButton#ThemeToggleButton {{
    background-color: {T["BG_FIELD"]};
    border: 1px solid {T["BORDER_FIELD"]};
    border-radius: 6px;
    height: 26px; /* Bằng khít chiều cao với QComboBox#HeaderLangMenu */
    min-width: 36px;
    max-width: 36px;
    padding: 0px;
}}
QPushButton#ThemeToggleButton:hover {{
    background-color: {T["BORDER_FIELD"]}; /* Tạo hiệu ứng sáng nhẹ lên khi hover */
}}

QMessageBox {{
    background-color: {T["BG_PANEL"]};
}}

QMessageBox QLabel {{
    font-family: "Arial";
    background: transparent;
    min-width: 240px;   /* Hạ từ 350px/400px xuống 240px để khung gọn gàng ôm sát chữ */
    padding-top: 10px;
    padding-bottom: 10px;
    padding-left: 5px;
}}

/* Giữ nút OK nằm gọn gàng ở góc dưới phải */
QMessageBox QPushButton {{
    background-color: {T["BG_FIELD"]};
    border: 1px solid {T["BORDER_FIELD"]};
    color: {T["TEXT_PRIMARY"]};
    font-family: "Arial";
    font-size: 12px;
    font-weight: 600;
    padding: 5px 20px;
    border-radius: 6px;
    min-width: 65px;
    margin-bottom: 4px;
}}

QMessageBox QPushButton:hover {{
    background-color: {T["BORDER_FIELD"]};
}}
"""


# ═══════════════════════════════════════════════════════════════════════════════
#  BACKWARD COMPAT — giữ biến APP_STYLESHEET cho code cũ
# ═══════════════════════════════════════════════════════════════════════════════

APP_STYLESHEET = build_stylesheet("light")
