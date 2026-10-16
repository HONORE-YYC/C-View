"""Playback state machine, independently testable without a Qt event loop."""
from time import monotonic

from .engine import Engine
from .language import CError


class Controller:
    def __init__(self, source, max_steps=100000):
        self.source, self.max_steps = source, max_steps
        self.engine = Engine(source, max_steps)
        self.targets = self.engine.program.targets()
        self.state, self.message = 'ready', '准备就绪'
        self.error = None
        self._seek_target = None

    def reset(self):
        self.engine = Engine(self.source, self.max_steps)
        self.state, self.message, self.error = 'ready', '已重置', None
        self._seek_target = None

    def play(self):
        if self.state in ('finished', 'stopped', 'error'):
            self.reset()
        self.state = 'seeking' if self._seek_target else 'running'
        self.message = '正在定位语句…' if self._seek_target else '正在演示'

    def pause(self):
        if self.state in ('running', 'seeking'):
            self.state, self.message = 'paused', '已暂停；单步执行或继续演示'

    def stop(self):
        self.state, self.message = 'stopped', '已停止，保留最后画面；再次播放从头开始'
        self._seek_target = None

    def seek(self, location):
        if self.state in ('finished', 'stopped', 'error'):
            self.reset()
        self._seek_target = (location.line, location.column, location.kind)
        self.state, self.message = 'seeking', f'正在定位第 {location.line} 行…'

    def _advance(self):
        event = self.engine.step()
        if self.engine.peek() is None:
            self.state = 'finished'
            self.message = '程序已结束' if not self._seek_target else '程序已结束，目标语句未到达；可重置后重试'
            self._seek_target = None
        return event

    def _fail(self, error):
        self.error = error
        self.state, self.message = 'error', str(error)
        self._seek_target = None

    def step(self):
        if self.state in ('finished', 'stopped', 'error'):
            self.reset()
        self._seek_target = None
        self.state, self.message = 'paused', '单步执行完成'
        try:
            return self._advance()
        except CError as error:
            self._fail(error)
            return None

    def tick(self, batch=40):
        events = []
        try:
            if self.state == 'running':
                event = self._advance()
                if event:
                    events.append(event)
            elif self.state == 'seeking':
                deadline = monotonic() + 0.012
                for _ in range(batch):
                    pending = self.engine.peek()
                    if pending is not None:
                        loc = pending.location
                        if (loc.line, loc.column, loc.kind) == self._seek_target:
                            self.state = 'paused'
                            self.message = f'已到第 {loc.line} 行第 {loc.column} 列，尚未执行；点击「单步」演示'
                            self._seek_target = None
                            break
                    event = self._advance()
                    if event:
                        events.append(event)
                    if self.state != 'seeking' or monotonic() >= deadline:
                        break
        except CError as error:
            self._fail(error)
        return events
