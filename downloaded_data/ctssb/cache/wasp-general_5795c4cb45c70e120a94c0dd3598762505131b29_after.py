
import pytest

from wasp_general.signals.proto import WSignalWatcherProto, WSignalSourceProto, WSignalCallbackProto
from wasp_general.signals.proto import WSignalProxyProto


def test_abstract():

	class W(WSignalWatcherProto):

		def wait(self, timeout=None):
			pass

		def has_next(self):
			pass

		def next(self):
			pass

	class C(WSignalCallbackProto):

		def __call__(self, signal_name, signal_source, signal_args=None):
			pass

	class S(WSignalSourceProto):

		def send_signal(self, signal_name, signal_args=None):
			pass

		def signals(self):
			pass

		def watch(self, signal_name, watcher=None):
			pass

		def remove_watcher(self, watcher):
			pass

		def callback(self, signal_name, callback):
			pass

		def remove_callback(self, signal_name, callback):
			pass

	pytest.raises(TypeError, WSignalWatcherProto)
	pytest.raises(NotImplementedError, WSignalWatcherProto.wait, None)
	pytest.raises(NotImplementedError, WSignalWatcherProto.wait, None, 1)
	pytest.raises(NotImplementedError, WSignalWatcherProto.has_next, None)
	pytest.raises(NotImplementedError, WSignalWatcherProto.next, None)

	pytest.raises(TypeError, WSignalSourceProto)
	pytest.raises(NotImplementedError, WSignalSourceProto.send_signal, None, 'signal')
	pytest.raises(NotImplementedError, WSignalSourceProto.send_signal, None, 'signal', 1)
	pytest.raises(NotImplementedError, WSignalSourceProto.signals, None)
	pytest.raises(NotImplementedError, WSignalSourceProto.watch, None, 'signal')
	pytest.raises(NotImplementedError, WSignalSourceProto.remove_watcher, None, W())
	pytest.raises(NotImplementedError, WSignalSourceProto.callback, None, 'signal', C())
	pytest.raises(NotImplementedError, WSignalSourceProto.remove_callback, None, 'signal', C())

	pytest.raises(TypeError, WSignalCallbackProto)
	pytest.raises(NotImplementedError, WSignalCallbackProto.__call__, None, S(), 'signal', 1)

	pytest.raises(TypeError, WSignalProxyProto.ProxiedMessageProto)
	pytest.raises(NotImplementedError, WSignalProxyProto.ProxiedMessageProto.is_weak, None)
	pytest.raises(NotImplementedError, WSignalProxyProto.ProxiedMessageProto.signal_source, None)
	pytest.raises(NotImplementedError, WSignalProxyProto.ProxiedMessageProto.signal_name, None)
	pytest.raises(NotImplementedError, WSignalProxyProto.ProxiedMessageProto.signal_arg, None)

	pytest.raises(TypeError, WSignalProxyProto)
	assert(issubclass(WSignalProxyProto, WSignalWatcherProto) is True)

	pytest.raises(NotImplementedError, WSignalProxyProto.watch, None, S(), 'signal')
	pytest.raises(NotImplementedError, WSignalProxyProto.remove_watcher, None, S(), 'signal')
	pytest.raises(NotImplementedError, WSignalProxyProto.wait, None)
	pytest.raises(NotImplementedError, WSignalProxyProto.wait, None, 1)
	pytest.raises(NotImplementedError, WSignalProxyProto.has_next, None)
	pytest.raises(NotImplementedError, WSignalProxyProto.next, None)
