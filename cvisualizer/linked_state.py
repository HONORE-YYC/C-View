"""Presentation-only linked node lifetime, advanced once per emitted event."""
from .pointers import Pointer


class LinkedState:
    def __init__(self, types):
        self.types = types
        self.head_cells = {}
        self.orphan_since = {}

    def discover(self, snapshot):
        for cell in sorted(snapshot.values(), key=lambda c: c['identity']):
            base = cell['type'][:-1] if cell['type'].endswith('*') else None
            if base in self.types and 'struct_owner' not in cell:
                self.head_cells.setdefault(base, cell['identity'])

    def decorate(self, snapshot, live, number, extra=()):
        self.discover(snapshot)
        nodes = {cell['identity']: (name, cell) for name, cell in snapshot.items() if cell.get('linked_node')}
        all_cells = list(snapshot.items()) + list(extra)
        by_identity = {cell['identity']: cell for _, cell in all_cells}
        def target(cell):
            value = cell.get('value') if cell else None
            return value.identity if isinstance(value, Pointer) else 'unknown'
        def chain(identity):
            seen = set()
            while identity in nodes and identity not in seen:
                seen.add(identity)
                name, cell = nodes[identity]
                identity = target(snapshot.get(name + '.' + cell['linked_node']['next']))
            return seen, identity is None
        heads = {target(by_identity.get(identity)) for identity in self.head_cells.values()}
        complete = set()
        for head in heads:
            path, valid = chain(head)
            if valid:
                complete |= path
        retained = set()
        node_names = {name: identity for identity, (name, _) in nodes.items()}
        owners = {cell['identity']: node_names[name.rsplit('.', 1)[0]]
                  for name, cell in all_cells
                  if '.' in name and name.rsplit('.', 1)[0] in node_names}
        pending = [cell['identity'] for name, cell in all_cells
                   if name.split('.', 1)[0].split('[', 1)[0] in live]
        visited = set()
        while pending:
            identity = pending.pop()
            if identity in visited:
                continue
            visited.add(identity)
            if identity in owners:
                pending.append(owners[identity])
            if identity in nodes:
                retained.add(identity)
                name, cell = nodes[identity]
                pending.append(target(snapshot.get(name + '.' + cell['linked_node']['next'])))
            cell = by_identity.get(identity)
            if cell:
                destination = target(cell)
                if destination != 'unknown':
                    pending.append(destination)
        for identity, (name, cell) in nodes.items():
            cell['linked_head'] = identity in heads
            orphan = identity not in complete
            if orphan:
                self.orphan_since.setdefault(identity, number)
            else:
                self.orphan_since.pop(identity, None)
            cell['linked_hidden'] = bool(orphan and identity not in retained and self.orphan_since[identity] < number)
        return snapshot
