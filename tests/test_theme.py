import pytest
from PySide6.QtGui import QColor, QTextCursor
from cvisualizer.window import MainWindow
from cvisualizer.theme import neutral_color


@pytest.mark.parametrize('paused', [False, True])
def test_toggle_preserves_execution_editor_and_scene(app, paused):
    window = MainWindow()
    window.load_code('int x = 1;\nx = x + 2;\n', [])
    window.step()
    cursor = window.editor.textCursor()
    cursor.setPosition(1)
    cursor.setPosition(4, QTextCursor.MoveMode.KeepAnchor)
    window.editor.setTextCursor(cursor)
    controller = window.controller
    items = set(window.visuals.scene().items())
    animation = window.visuals.motion.animation
    animation.setDuration(10000)
    animation.start()
    animation.setCurrentTime(300)
    if paused:
        animation.pause()
    state = animation.state()
    elapsed = animation.currentTime()
    scroll = window.editor.verticalScrollBar().value()
    document = window.editor.document()
    modified = document.isModified()
    window.theme_button.click()
    assert window.dark_mode
    assert window.controller is controller
    assert window.editor.textCursor().selectedText() == 'nt '
    assert window.editor.document() is document
    assert document.isModified() == modified
    assert set(window.visuals.scene().items()) == items
    assert animation.state() == state
    assert animation.currentTime() == elapsed
    assert window.editor.verticalScrollBar().value() == scroll
    assert window.visuals.backgroundBrush().color() == QColor('#000000')
    window.theme_button.click()
    assert not window.dark_mode
    assert window.visuals.backgroundBrush().color() == QColor('#ffffff')


def test_neutral_colors_leave_semantic_colors(app):
    assert neutral_color('#334155', True) == QColor('#ffffff')
    for color in ('#dcfce7', '#f3e8ff', '#0f766e', '#2563eb'):
        assert neutral_color(color, True) == QColor(color)


def test_scene_labels_and_pointer_background_restore_without_recreation(app):
    from cvisualizer.views import MemoryView
    from cvisualizer.animations import IndexPointer
    from cvisualizer.theme import apply_scene_theme
    view = MemoryView()
    label = view.label('neutral', 0, 0)
    semantic = view.label('green', 0, 30, color='#16a34a')
    pointer = IndexPointer('i')
    view.scene().addItem(pointer)
    backgrounds = [item for item in pointer.childItems() if hasattr(item, '_theme_colors')]
    assert backgrounds
    for dark in (True, False):
        apply_scene_theme(view.scene(), dark)
        assert label.defaultTextColor() == QColor('#ffffff' if dark else '#334155')
        assert semantic.defaultTextColor() == QColor('#16a34a')
        assert backgrounds[0].brush().color().name() == ('#000000' if dark else '#ffffff')
        assert backgrounds[0].brush().color().alpha() == 225


def test_colored_cell_contrast_survives_label_updates_and_theme_roundtrip(app):
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QImage, QPainter
    from cvisualizer.views import MemoryView
    from cvisualizer.boolean_animation import BooleanSummary
    from cvisualizer.theme import apply_scene_theme
    view = MemoryView()
    cell = view.box('x', 1, 0, 0, 130)
    overlay = BooleanSummary(view.scene(), {'rect': QRectF(0, 60, 400, 130),
        'evaluations': [{'expression': 'x > 0', 'result': True, 'operands': [1, 0]}]})
    apply_scene_theme(view.scene(), True)
    effect = cell.value_label.graphicsEffect()
    assert effect is not None and effect.isEnabled()
    assert overlay.label.graphicsEffect().isEnabled()
    cell.value_label.setPlainText('x = 2')  # Function replay updates the same label.
    overlay.frame(.6)
    assert cell.value_label.graphicsEffect() is effect and effect.isEnabled()
    assert overlay.label.graphicsEffect().isEnabled()
    assert overlay.result_label.brush().color() == QColor('#166534')
    assert not overlay.result_label.graphicsEffect().isEnabled()

    def render():
        image = QImage(450, 220, QImage.Format.Format_ARGB32)
        image.fill(QColor('#000000'))
        painter = QPainter(image)
        view.scene().render(painter, QRectF(0, 0, 450, 220), QRectF(0, 0, 450, 220))
        painter.end()
        return image

    with_shadow = render()
    effect.setEnabled(False)
    assert with_shadow != render()  # The contrast treatment reaches rendered pixels.
    effect.setEnabled(True)
    apply_scene_theme(view.scene(), False)
    assert not effect.isEnabled()
    assert not overlay.label.graphicsEffect().isEnabled()
    assert cell.value_label.defaultTextColor() == QColor('#172b4d')
    assert cell.brush().color() == QColor('#dcfce7')
