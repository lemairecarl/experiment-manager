from abc import ABC, abstractmethod


class ComputePlatform(ABC):
    @abstractmethod
    def submit(self, task, resume=False) -> str:
        """Submit a task and return the plaform specific task id.

        If resume=True, run script in already-existing output path.
        """
        pass

    @abstractmethod
    def fetch_logs(self, task, keys=None):
        """Return a dict of logs.

        Example: {
            'out': '...',
            'err': '...',
            'metric_loss': '...'
        }
        """
        pass

    @abstractmethod
    def cancel(self, task):
        """Cancel a task."""
        pass

    @abstractmethod
    def get_statuses(self, job_ids) -> dict:
        """Return a dict mapping job ids to their statuses.

        Example: {
            '1234': TaskStatus.Running,
            '5678': TaskStatus.Waiting
        }
        """
        pass
