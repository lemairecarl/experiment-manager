import time
from pathlib import Path
from typing import List, Iterable, Dict

import redis.exceptions
from redis import Redis
from rq import Queue
from rq.job import Job, cancel_job as cancel_rq_job

from hypertrainer.computeplatform import ComputePlatform
from hypertrainer.computeplatformtype import ComputePlatformType
from hypertrainer.htplatform_worker import run, get_jobs_info, get_logs, ping, raise_exception, delete_job, \
    cancel_job
from hypertrainer.utils import TaskStatus, get_python_env_command, config_context


ConnectionError = redis.exceptions.ConnectionError


def check_connection(redis_conn):
    try:
        redis_conn.ping()
    except redis.exceptions.ConnectionError as e:
        msg = e.args[0]
        msg += '\nPlease make sure redis-server is running, and accessible.'
        e.args = (msg,) + e.args[1:]
        raise e


class HtPlatform(ComputePlatform):
    """The HT (HyperTrainer) Platform allows to send jobs to one or more Linux machines.

    Each participating worker consumes jobs from a global queue. There can be several workers per machine.
    """

    def __init__(self, same_thread=False):
        with config_context() as config:
            self.worker_hostnames = config['ht_platform']['worker_hostnames']

            redis_conn = Redis(port=config['ht_platform']['redis_port'])
            check_connection(redis_conn)
            self.redis_conn = redis_conn

        self.jobs_queue = Queue(name='jobs', connection=redis_conn, is_async=not same_thread)
        self.worker_queues: Dict[str, Queue] = {h: Queue(name=h, connection=redis_conn, is_async=not same_thread)
                                                for h in self.worker_hostnames}

    def submit(self, task, resume=False):
        output_path = Path(task.output_root) / str(task.uuid)
        task.output_path = str(output_path)
        python_env_command = get_python_env_command(Path(task.project_path), ComputePlatformType.HT.value)
        job = self.jobs_queue.enqueue(run, job_timeout=-1, kwargs=dict(
            script_file=Path(task.script_file),
            output_path=output_path,
            python_env_command=python_env_command,
            config_dump=task.dump_config(),
            resume=resume))
        # At this point, we only know the rq job id. No pid since the job might have to wait.
        return job.id

    def fetch_logs(self, task, keys=None):
        if task.hostname == '':  # The job hasn't been consumed yet
            return {}
        rq_job = self.worker_queues[task.hostname].enqueue(get_logs, args=(task.output_path,), ttl=2, result_ttl=2)
        logs = wait_for_result(rq_job)
        return logs

    def cancel(self, task):
        cancel_rq_job(task.job_id, connection=self.redis_conn)  # This ensures the job will not start

        if task.hostname == '':
            print(f'Cannot send cancellation for {task.uuid}: no assigned worker hostname')
        else:
            self.worker_queues[task.hostname].enqueue(cancel_job, args=(task.job_id,), ttl=4)

    def update_tasks(self, tasks):
        # TODO only check requested ids

        for t in tasks:
            assert t.status.is_active
            if t.status != TaskStatus.Waiting:  # Waiting will not be found until they are picked up
                t.status = TaskStatus.Unknown  # State is unknown, unless we find the task in a worker db
        job_id_to_task = {t.job_id: t for t in tasks}

        info_dicts = self._get_info_dict_for_each_worker()
        for hostname, local_db in zip(self.worker_hostnames, info_dicts):
            if local_db is None:
                continue  # Did not receive an answer from worker
            for job_id in set(local_db.keys()).intersection(job_id_to_task.keys()):
                # For each task in the intersection of (tasks to update) and (tasks in worker db)
                t = job_id_to_task[job_id]
                job_info = local_db[job_id]
                t.status = TaskStatus(job_info['status'])
                t.hostname = hostname

    def delete(self, task):
        if task.hostname == '':
            print(f'Cannot perform worker deletion for {task.uuid}: no assigned worker hostname')
        else:
            self.worker_queues[task.hostname].enqueue(delete_job, args=(task.job_id, task.output_path), ttl=4)

    def _get_info_dict_for_each_worker(self):
        rq_jobs = [q.enqueue(get_jobs_info, ttl=2, result_ttl=2) for q in self.worker_queues.values()]
        results = wait_for_results(rq_jobs, raise_exc=False)
        return results

    def ping_workers(self):
        rq_jobs = [q.enqueue(ping, ttl=2, result_ttl=2, args=(h,)) for h, q in self.worker_queues.items()]
        results = wait_for_results(rq_jobs)
        return results

    def raise_exception_in_worker(self, exc_type, queue_name):
        self.worker_queues[queue_name].enqueue(raise_exception, ttl=2, result_ttl=2, args=(exc_type,))


def wait_for_result(rq_job: Job, interval_secs=1, tries=4, raise_exc=True):
    for i in range(tries):
        if rq_job.result is not None:
            return rq_job.result
        else:
            time.sleep(interval_secs)
    if raise_exc:
        raise TimeoutError
    return None


def wait_for_results(rq_jobs: Iterable[Job], interval_secs=1, tries=4, raise_exc=True):
    assert tries >= 1
    for i in range(tries):
        results = [j.result for j in rq_jobs]
        if any(r is None for r in results):
            time.sleep(interval_secs)
        else:
            return results
    if raise_exc:
        raise TimeoutError
    # noinspection PyUnboundLocalVariable
    return results
