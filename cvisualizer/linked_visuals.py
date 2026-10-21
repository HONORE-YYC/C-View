"""Identity based, viewport bounded linked-node scene and shared-clock transitions."""
import math
import heapq
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPen, QBrush, QPainterPath, QPolygonF, QFont, QFontMetricsF
from PySide6.QtWidgets import QGraphicsRectItem, QGraphicsTextItem, QGraphicsPathItem, QGraphicsPolygonItem
from .pointers import Pointer
from .value_format import display
from .animations import smooth
from .theme import neutral_color, track_color

RED = '#dc2626'


def node_model(snapshot):
    nodes = {}
    for name, cell in snapshot.items():
        fields = cell.get('linked_node')
        if not fields or not cell.get('is_struct') or cell.get('linked_hidden'):
            continue
        data_name, next_name = name+'.'+fields['data'], name+'.'+fields['next']
        value = snapshot.get(next_name, {}).get('value')
        target = value.identity if isinstance(value, Pointer) else None
        nodes[cell['identity']] = dict(name=name, data=snapshot.get(data_name, {}).get('value'),
            data_name=data_name, next_name=next_name, next_value=value, target=target, aliases=[], head=bool(cell.get('linked_head')),
            status='未初始化' if value is None else ('NULL' if isinstance(value, Pointer) and target is None else '悬空'))
    for node in nodes.values():
        if node['target'] in nodes:
            node['status'] = '连接'
    next_members = {name+'.'+cell['linked_node']['next'] for name, cell in snapshot.items() if cell.get('linked_node')}
    for name, cell in snapshot.items():
        value = cell.get('value')
        if isinstance(value, Pointer) and value.identity in nodes and name not in next_members:
            nodes[value.identity]['aliases'].append(name)
            if cell.get('linked_head'):
                nodes[value.identity]['head'] = True
    return nodes


def layout(model, width, top):
    """Walk each component iteratively; cycles and shared tails terminate once."""
    incoming = {node['target'] for node in model.values() if node['target'] in model}
    starts = [identity for identity in model if model[identity].get('head')]
    starts += [identity for identity in model if identity not in incoming and identity not in starts]
    order, seen = [], set()
    for identity in starts+list(model):
        while identity in model and identity not in seen:
            seen.add(identity); order.append(identity)
            identity = model[identity]['target']
    columns = max(1, int((width-2)//124))
    positions = {identity: QPointF(20+(index % columns)*124, top+(index//columns)*104)
                 for index, identity in enumerate(order)}
    return positions, top+math.ceil(len(order)/columns)*104


def text(parent, value, x, y, width, size=9, color='#991b1b'):
    item = QGraphicsTextItem(parent)
    item.setFont(QFont('Microsoft YaHei UI', size))
    item.setDefaultTextColor(neutral_color(color))
    track_color(item, 'text', color)
    item.setToolTip(value)
    item.setPlainText(QFontMetricsF(item.font()).elidedText(value, Qt.TextElideMode.ElideRight, width))
    item.setPos(x, y)
    return item


class NodeCard(QGraphicsRectItem):
    def __init__(self, node, parent):
        super().__init__(0, 0, 86, 40, parent)
        self.setPen(QPen(QColor(RED), 2))
        self.setBrush(QBrush(QColor('#fee2e2')))
        self.setZValue(2)
        self.setToolTip(node['name']+'\n'+node['data_name']+' = '+display(node['data'])+'\n'+node['next_name']+': '+node['status']+'\n'+str(node['next_value']))
        self.name_label = text(self, '' if node['name'].startswith('堆#') else node['name'], 0, -23, 86, 8, '#64748b')
        aliases = ', '.join(node['aliases'])
        self.alias_label = text(self, '↓ '+aliases if aliases else '', 0, -42, 86, 8, '#64748b')
        self.alias_label.setToolTip(aliases)
        self.data_box = QGraphicsRectItem(0, 0, 86, 22, self)
        self.data_box.setPen(QPen(Qt.PenStyle.NoPen))
        self.data_box._linked = True
        label = '未初始化' if node['data'] is None else display(node['data'])
        self.data_box.value_label = text(self.data_box, label, 2, -2, 78)
        self.next_label = text(self, node['next_name'].rsplit('.', 1)[-1]+': '+node['status'], 2, 19, 78, 7)


class Edge(QGraphicsPathItem):
    def __init__(self, parent):
        super().__init__(parent)
        self.setPen(QPen(QColor(RED), 2))
        self.head = QGraphicsPolygonItem(self)
        self.head.setBrush(QBrush(QColor(RED)))
        self.head.setPen(QPen(Qt.PenStyle.NoPen))
        self.label = text(self, '', 0, 0, 170, 8, '#64748b')
        self.setZValue(1)

    def route(self, start, end, status='', obstacles=(), directions=(QPointF(1, 0), QPointF(-1, 0))):
        if end is None:
            end = start+QPointF(26, 0)
        points = clear_route(start, end, obstacles, directions)
        cleaned = []
        for point in points:
            if cleaned and point == cleaned[-1]:
                continue
            while len(cleaned) >= 2 and ((cleaned[-2].x() == cleaned[-1].x() == point.x()) or (cleaned[-2].y() == cleaned[-1].y() == point.y())):
                cleaned.pop()
            cleaned.append(point)
        points = cleaned
        path = QPainterPath(points[0])
        for index in range(1, len(points)-1):
            previous, corner, following = points[index-1:index+2]
            before, after = corner-previous, following-corner
            length_a, length_b = math.hypot(before.x(), before.y()), math.hypot(after.x(), after.y())
            radius = min(5., length_a/2, length_b/2)
            if length_a and length_b:
                path.lineTo(corner-before*(radius/length_a))
                path.quadTo(corner, corner+after*(radius/length_b))
        path.lineTo(points[-1])
        self.setPath(path)
        tip, prev = path.pointAtPercent(1), path.pointAtPercent(.98)
        angle = math.atan2(tip.y()-prev.y(), tip.x()-prev.x())
        backward = QPointF(math.cos(angle)*7, math.sin(angle)*7)
        side = QPointF(-math.sin(angle)*3, math.cos(angle)*3)
        self.head.setPolygon(QPolygonF([tip, tip-backward+side, tip-backward-side]))
        self.setToolTip(status)
        self.label.setPlainText('')
        self.label.setPos(end+QPointF(-12, -24))


def clear_route(start, end, obstacles, directions, clearance=8):
    """Orthogonal visibility grid in the empty gutters, with rounded corners.

    Eight pixels of clearance protects the curved corner and the arrowhead.
    Coordinates follow moving cards, so lanes move continuously with them.
    """
    rects = [rect.adjusted(-clearance, -clearance, clearance, clearance) for rect in obstacles]
    source, destination = start+directions[0]*10, end+directions[1]*10
    xs = sorted({source.x(), destination.x(), *[v for r in rects for v in (r.left(), r.right())]})
    ys = sorted({source.y(), destination.y(), *[v for r in rects for v in (r.top(), r.bottom())]})
    def blocked(a, b):
        for r in rects:
            if a[1] == b[1]:
                if r.top()+.01 < a[1] < r.bottom()-.01 and max(a[0], b[0]) > r.left()+.01 and min(a[0], b[0]) < r.right()-.01:
                    return True
            elif r.left()+.01 < a[0] < r.right()-.01 and max(a[1], b[1]) > r.top()+.01 and min(a[1], b[1]) < r.bottom()-.01:
                return True
        return False
    # Prefer one continuous topology: down the source gap, along the
    # row gutter, outside the right edge, and back through the target gutter.
    # Only crowded transient nodes require a visibility-grid detour.
    if directions[0] == QPointF(1, 0) and directions[1] == QPointF(-1, 0):
        if abs(start.y()-end.y()) < .01 and 0 < end.x()-start.x() < 55:
            candidate = [start, end]
        else:
            source_gutter, target_gutter = start.y()+36, end.y()+36
            if 0 < end.y()-start.y() <= 104.01:
                target_gutter = source_gutter
            outer = max([source.x(), destination.x(), *[r.right() for r in rects]])+12
            candidate = [start, source, QPointF(source.x(), source_gutter), QPointF(outer, source_gutter),
                         QPointF(outer, target_gutter), QPointF(destination.x(), target_gutter), destination, end]
        if all(not blocked((a.x(), a.y()), (b.x(), b.y())) for a, b in zip(candidate[1:-2], candidate[2:-1])) and (len(candidate) > 2 or not any(r.adjusted(clearance,clearance,-clearance,-clearance).contains((start+end)*.5) for r in rects)):
            return candidate
    origin = (xs.index(source.x()), ys.index(source.y()))
    goal = (xs.index(destination.x()), ys.index(destination.y()))
    queue, costs, parents = [(0., origin)], {origin: 0.}, {}
    while queue:
        _, current = heapq.heappop(queue)
        if current == goal:
            break
        x, y = current
        for neighbor in ((x-1,y), (x+1,y), (x,y-1), (x,y+1)):
            nx, ny = neighbor
            if not (0 <= nx < len(xs) and 0 <= ny < len(ys)):
                continue
            a, b = (xs[x], ys[y]), (xs[nx], ys[ny])
            if blocked(a, b):
                continue
            cost = costs[current]+abs(a[0]-b[0])+abs(a[1]-b[1])
            if cost >= costs.get(neighbor, float('inf')):
                continue
            costs[neighbor], parents[neighbor] = cost, current
            heuristic = abs(xs[nx]-destination.x())+abs(ys[ny]-destination.y())
            heapq.heappush(queue, (cost+heuristic, neighbor))
    if goal not in costs and clearance > 2:
        return clear_route(start, end, obstacles, directions, 2)
    if goal not in costs:
        # Overlapping cards can temporarily occupy an attachment port. Route
        # through the shared outer gutter until a free port becomes available.
        gutter = max([start.y(), end.y(), *[r.bottom() for r in rects]])+12
        return [start, QPointF(source.x(), start.y()), QPointF(source.x(), gutter), QPointF(destination.x(), gutter), destination, end]
    route, cursor = [], goal
    while cursor != origin:
        route.append(QPointF(xs[cursor[0]], ys[cursor[1]]))
        cursor = parents[cursor]
    route.append(source)
    route.reverse()
    points = [start]
    for point in route+[end]:
        if len(points) >= 2 and ((points[-2].x() == points[-1].x() == point.x()) or (points[-2].y() == points[-1].y() == point.y())):
            points[-1] = point
        elif point != points[-1]:
            points.append(point)
    return points


def interpolate_position(start, end, t):
    """Carry a wrapping card through the empty row gutter rather than peers."""
    if abs(end.y()-start.y()) > 1 and abs(end.x()-start.x()) > 86:
        middle = (start.y()+end.y())/2
        if t < .25:
            return QPointF(start.x(), start.y()+(middle-start.y())*smooth(t*4))
        if t < .75:
            return QPointF(start.x()+(end.x()-start.x())*smooth((t-.25)*2), middle)
        return QPointF(end.x(), middle+(end.y()-middle)*smooth((t-.75)*4))
    return start+(end-start)*t


class LinkedLayer:
    def __init__(self, view, snapshot, before, width, top, animate):
        self.model, self.old_model = node_model(snapshot), node_model(before)
        self.positions, self.bottom = layout(self.model, width, top)
        self.origins, old_bottom = layout(self.old_model, width, top)
        self.nodes, self.edges = {}, []
        self.animate = animate
        if animate:
            self.bottom = max(self.bottom, old_bottom)
        offset = view._draw_offset
        low, high = offset+50, offset+view.viewport().height()+150
        identities = set(self.positions)
        if animate:
            identities.update(self.origins)
        for identity in identities:
            destination = self.positions.get(identity, self.origins.get(identity))
            origin = self.origins.get(identity, destination)
            # Only create objects near either endpoint, keeping scene size bounded.
            if not (low-104 <= destination.y() <= high or animate and low-104 <= origin.y() <= high):
                continue
            node = self.model.get(identity, self.old_model.get(identity))
            card = NodeCard(node, view._content_parent)
            self.nodes[identity] = card
            if identity in self.model:
                cell = snapshot.get(node['data_name'])
                if cell:
                    view.boxes[node['data_name'], None, cell['identity']] = card.data_box
            card.setPos(destination-QPointF(0, offset))
        for identity in self.nodes:
            node = self.model.get(identity)
            old = self.old_model.get(identity)
            specs = [(node, False)] if node else []
            if animate and old and (not node or old['target'] != node['target'] or old['status'] != node['status']):
                specs.append((old, True))
            for spec, outgoing in specs:
                edge = Edge(view._content_parent)
                changed = not old or not node or old['target'] != node['target'] or old['status'] != node['status']
                self.edges.append((identity, spec, outgoing, changed, edge))
        self.aliases = {}
        if animate:
            old_aliases = {name: identity for identity, node in self.old_model.items() for name in node['aliases']}
            new_aliases = {name: identity for identity, node in self.model.items() for name in node['aliases']}
            for card in self.nodes.values():
                card.alias_label.setVisible(False)
            # Alias labels move between object identities even when their spelling
            # and the underlying node layout stay unchanged (ordinary traversal).
            grouped = {}
            alias_names = list(dict.fromkeys([*old_aliases, *new_aliases]))
            totals = {}
            for name in alias_names:
                group_id = new_aliases.get(name) if new_aliases.get(name) in self.nodes else old_aliases.get(name)
                totals.setdefault(group_id, []).append(name)
            for name in alias_names:
                old_id, new_id = old_aliases.get(name), new_aliases.get(name)
                if old_id not in self.nodes and new_id not in self.nodes:
                    continue
                group_id = new_id if new_id in self.nodes else old_id
                lane = grouped.get(group_id, 0)
                grouped[group_id] = lane+1
                if lane >= 3:
                    continue
                start = self.origins.get(old_id, self.positions.get(new_id))
                end = self.positions.get(new_id, self.origins.get(old_id))
                if start is None or end is None:
                    continue
                slot_width = 86/min(3, len(totals[group_id]))
                label_text = '↓ '+name if lane < 2 or len(totals[group_id]) <= 3 else '↓ +'+str(len(totals[group_id])-2)
                label = text(view._content_parent, label_text, 0, 0, slot_width-4, 8, '#64748b')
                label.setToolTip(', '.join(totals[group_id]))
                label.setZValue(4)
                # Shared aliases occupy a single compact line; full spelling is
                # available in each tooltip without expanding node row heights.
                shift = QPointF(lane*slot_width, -42-offset)
                self.aliases[name] = (label, start+shift, end+shift, old_id is not None, new_id is not None)
        self.offset = offset
        self.frame(0 if animate else 1)

    def frame(self, progress):
        t = smooth(progress)
        for identity, card in self.nodes.items():
            end = self.positions.get(identity, self.origins.get(identity))
            start = self.origins.get(identity, end)
            card.setPos(interpolate_position(start, end, t)-QPointF(0, self.offset))
            opacity = (t if identity not in self.old_model else 1) if identity in self.model else 1-t
            card.setOpacity(opacity if self.animate else 1)
            card.setVisible(not (progress >= 1 and identity not in self.model))
        for label, start, end, had_old, has_new in self.aliases.values():
            label.setPos(interpolate_position(start, end, t))
            label.setOpacity((1 if had_old else t) if has_new else 1-t)
        for identity, spec, outgoing, changed, edge in self.edges:
            card = self.nodes[identity]
            target = self.nodes.get(spec['target'])
            cards = [other for other in self.nodes.values() if other.isVisible() and other.opacity() > .001]
            def port(item, incoming=False):
                rect = item.mapRectToParent(item.rect())
                sides = [('left', QPointF(-1, 0)), ('top', QPointF(0, -1)), ('bottom', QPointF(0, 1)), ('right', QPointF(1, 0))] if incoming else [('right', QPointF(1, 0)), ('bottom', QPointF(0, 1)), ('top', QPointF(0, -1)), ('left', QPointF(-1, 0))]
                others = [other.mapRectToParent(other.rect()).adjusted(-8, -8, 8, 8) for other in cards if other is not item]
                for side, direction in sides:
                    for fraction in (.5, .2, .8):
                        point = QPointF(rect.left() if side == 'left' else rect.right() if side == 'right' else rect.left()+rect.width()*fraction,
                                        rect.top() if side == 'top' else rect.bottom() if side == 'bottom' else rect.top()+rect.height()*fraction)
                        if not any(r.contains(point+direction*distance) for r in others for distance in (0, 5, 10)):
                            return point, direction
                return rect.bottomRight(), QPointF(1, 0)
            start, start_direction = port(card)
            end, end_direction = port(target, True) if target else (None, QPointF(-1, 0))
            status = '' if target else ('屏外 →' if spec['target'] in self.model else spec['status'])
            edge.route(start, end, status, [other.mapRectToParent(other.rect()) for other in cards], (start_direction, end_direction))
            opacity = 1-t if outgoing else (t if changed and self.animate else 1)
            edge.setOpacity(opacity*card.opacity())
