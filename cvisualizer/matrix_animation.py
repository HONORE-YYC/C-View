"""Matrix drawer motion driven by the existing scene animation clock."""
from .animations import smooth


def frame(items, progress):
    amount = smooth(progress/.2) if progress < .2 else (1. if progress <= .75 else 1-smooth((progress-.75)/.25))
    for item in items:
        item.setPos(item.matrix_origin + item.matrix_delta*amount)
        item.setZValue(3 if amount else -.5)
        item.value_label.setVisible(amount > .05)
        if hasattr(item, 'owner_label'):
            item.owner_label.setVisible(amount > .05)
