import core.task
import os
import shutil


class RemoveDirectoryTask(core.task.Task):
	def execute_task(self, parameters=None):
		self._check_mandatory_parameters(['path'], parameters)
		path = parameters['path']
			
		if not os.path.exists(path):
			raise core.task.TaskGenericException('path %s does not exist' % path)
		else:
			oshutils.rmtree(path)
