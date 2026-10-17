"""Playback state machine, independently testable without a Qt event loop."""
from time import monotonic

from .engine import Engine
from .language import CError
from .formatted_io import InputCancelled


class Controller:
    def __init__(self, source, max_steps=100000, input_provider=None):
        self.source, self.max_steps = source, max_steps
        self.input_provider = input_provider
        self.engine = Engine(source, max_steps)
        self.engine.runtime.input_provider = input_provider
        self.targets = self.engine.program.targets()
        self.state, self.message = 'ready', '准备就绪'
        self.error = None
        self._seek_target = None
        self._play_target = False
        self._detail_playing = False
        self._target_function = None

    def reset(self):
        self.engine = Engine(self.source, self.max_steps)
        self.engine.runtime.input_provider = self.input_provider
        self.targets = self.engine.program.targets()
        self.state, self.message, self.error = 'ready', '已重置', None
        self._seek_target = None
        self._play_target = False
        self._detail_playing = False

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
        self._play_target = False
        self._detail_playing = False

    def seek(self, location):
        if self.state in ('finished', 'stopped', 'error'):
            self.reset()
        self._seek_target = (location.line, location.column, location.kind)
        self._play_target = False
        self._detail_playing = False
        self._target_function = self.engine.program.target_functions.get(location)
        self.state, self.message = 'seeking', f'正在定位第 {location.line} 行…'

    def play_statement(self, location):
        self.seek(location)
        self._play_target = True

    def _advance(self, expand_calls=False):
        event = self.engine.step(expand_calls=expand_calls)
        if self.engine.peek() is None:
            self.state = 'finished'
            self.message = '程序已结束' if not self._seek_target else '程序已结束，目标语句未到达；可重置后重试'
            self._seek_target = None
        return event

    def _fail(self, error):
        if isinstance(error, InputCancelled):
            self.error = None
            self.state, self.message = 'paused', str(error)
            return
        self.error = error
        self.state, self.message = 'error', str(error)
        self._seek_target = None
        self._play_target = False
        self._detail_playing = False

    def step(self, expand_calls=False):
        if self.state in ('finished', 'stopped', 'error'):
            self.reset()
        self._seek_target = None
        self.state, self.message = 'paused', '单步执行完成'
        try:
            event = self._advance(expand_calls or self.engine.has_detail)
            if expand_calls and self.engine.has_detail:
                self._detail_playing = True
                self.state, self.message = 'running', '正在展开函数演示'
            elif not self.engine.has_detail:
                self._detail_playing = False
            return event
        except CError as error:
            self._fail(error)
            return None

    def tick(self, batch=40):
        events = []
        try:
            if self.state == 'running':
                detailing = self._detail_playing
                event = self._advance(expand_calls=detailing)
                if event:
                    events.append(event)
                if detailing and not self.engine.has_detail:
                    self._detail_playing = False
                    if self.state != 'finished':
                        self.state, self.message = 'paused', '函数演示完成，已返回调用处'
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
                            if self._play_target:
                                self._play_target = False
                                event = self.step(expand_calls=True)
                                if event:
                                    events.append(event)
                            break
                    expand = self.engine.has_detail or (
                        pending is not None and bool(self._target_function)
                        and self.engine.program.call_reaches(pending.functions, self._target_function))
                    event = self._advance(expand_calls=expand)
                    if event:
                        events.append(event)
                        if event.kind == 'function' and (event.line, event.column, event.kind) == self._seek_target:
                            self._seek_target = None
                            self.state, self.message = 'paused', '已进入函数，使用本次调用的实际参数'
                            if self._play_target:
                                self._play_target = False
                                self._detail_playing = True
                                self.state = 'running'
                            break
                    if self.state != 'seeking' or monotonic() >= deadline:
                        break
        except CError as error:
            self._fail(error)
        return events
