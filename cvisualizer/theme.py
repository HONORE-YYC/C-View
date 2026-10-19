"""Neutral theme colors. Semantic teaching colors are deliberately retained."""
from PySide6.QtGui import QColor, QBrush
from PySide6.QtWidgets import QApplication, QGraphicsTextItem, QGraphicsDropShadowEffect

TEXT = {'#000000', '#26354d', '#12243c', '#718096', '#334155', '#172b4d', '#64748b', '#0f172a', '#8794a7'}
SURFACE = {'#ffffff', '#f3f6fa'}


def is_dark():
    app = QApplication.instance()
    return bool(app and app.property('darkTheme'))


def neutral_color(light_color, dark=None):
    color = QColor(light_color)
    dark = is_dark() if dark is None else dark
    if dark and color.name() in TEXT | SURFACE:
        result = QColor('#ffffff' if color.name() in TEXT else '#000000')
        result.setAlpha(color.alpha())
        return result
    return color


def track_color(item, role, original):
    colors = getattr(item, '_theme_colors', {})
    colors[role] = QColor(original)
    item._theme_colors = colors


def cell_text_contrast(item, original, dark=None):
    """Keep white teaching labels legible on unchanged pale semantic fills.

    An item effect survives setPlainText/setText used during replay. It is
    disabled in light mode and for semantic colored text.
    """
    item._theme_cell_text = True
    dark = is_dark() if dark is None else dark
    effect = item.graphicsEffect()
    if effect is None:
        effect = QGraphicsDropShadowEffect()
        effect.setColor(QColor('#000000'))
        effect.setOffset(0, 0)
        effect.setBlurRadius(4)
        item.setGraphicsEffect(effect)
    effect.setEnabled(bool(dark and QColor(original).name() in TEXT))


def apply_scene_theme(scene, dark):
    for item in scene.items():
        colors = getattr(item, '_theme_colors', {})
        if not colors:
            if isinstance(item, QGraphicsTextItem):
                track_color(item, 'text', item.defaultTextColor())
            elif hasattr(item, 'brush') and item.brush().color().name() in TEXT | SURFACE:
                track_color(item, 'brush', item.brush().color())
            if hasattr(item, 'pen') and item.pen().color().name() in TEXT:
                track_color(item, 'pen', item.pen().color())
        for role, color in getattr(item, '_theme_colors', {}).items():
            mapped = neutral_color(color, dark)
            if getattr(item, '_theme_cell_text', False) and role in ('text', 'brush'):
                cell_text_contrast(item, color, dark)
            if role == 'text':
                item.setDefaultTextColor(mapped)
            elif role == 'brush':
                brush = item.brush()
                # Animation pulses temporarily own the brush. Repainting the
                # theme must not replace their live semantic color.
                if brush.color() not in (neutral_color(color, False), neutral_color(color, True)):
                    continue
                brush.setColor(mapped)
                item.setBrush(brush)
            else:
                pen = item.pen()
                pen.setColor(mapped)
                item.setPen(pen)


def stylesheet(light_style, dark):
    if not dark:
        return light_style
    return light_style + '''
QMainWindow, QDialog, QWidget, QMenu, QComboBox QAbstractItemView { background: #000000; color: #ffffff; }
QFrame#panel { background: #000000; border-color: #475569; }
QLabel#heading, QLabel#muted { color: #ffffff; }
QPushButton, QComboBox, QLineEdit, QSpinBox { background: #000000; color: #ffffff; border-color: #64748b; }
QPushButton:hover { background: #17202b; }
QPushButton:disabled { color: #8794a7; background: #000000; border-color: #334155; }
QPushButton#primary { background: #0f766e; color: white; }
QPlainTextEdit, QGraphicsView { background: #000000; color: #ffffff; selection-background-color: #24534f; }
QSplitter::handle, QSlider::groove:horizontal { background: #334155; }
QToolTip { color: #ffffff; background: #000000; border: 1px solid #64748b; }
'''
