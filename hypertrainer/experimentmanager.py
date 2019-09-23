from typing import Iterable

from ruamel.yaml import YAML

from hypertrainer.computeplatform import ComputePlatformType, platform_instances, list_platforms, get_platform
from hypertrainer.task import Task
from hypertrainer.db import get_db
from hypertrainer.hpsearch import generate as generate_hpsearch
from hypertrainer.utils import resolve_path

yaml = YAML()


class ExperimentManager:
    @staticmethod
    def get_all_tasks(do_update=False, proj=None):
        if do_update:
            ExperimentManager.update_statuses()
        # NOTE: statuses are requested asynchronously by the dashboard
        q = Task.select()
        if proj is not None:
            q = q.where(Task.project == proj)
        q = q.order_by(Task.id.desc())
        all_tasks = list(q)
        return all_tasks

    @staticmethod
    def get_tasks(platform: ComputePlatformType, proj=None):
        ExperimentManager.update_statuses(platforms=[platform])  # TODO return tasks to avoid other db query?
        q = Task.select().where(Task.platform_type == platform)
        if proj is not None:
            q = q.where(Task.project == proj)
        q = q.order_by(Task.id.desc())
        tasks = list(q)
        for t in tasks:
            ExperimentManager.monitor(t)
        return tasks

    @staticmethod
    def update_statuses(platforms: list = None):
        if platforms is None:
            platforms = list_platforms()
        for ptype in platforms:
            platform = platform_instances[ptype]
            tasks = list(Task.select().where(Task.platform_type == ptype))
            tasks = [t for t in tasks if t.status.is_active()]
            if len(tasks) == 0:
                continue
            job_ids = [t.job_id for t in tasks]
            get_db().close()  # Close db since the following may take time
            statuses = platform.get_statuses(job_ids)
            get_db().connect()
            for t in tasks:
                t.status = statuses[t.job_id]
                t.save()

    @staticmethod
    def create_tasks(platform: str, script_file: str, config_file: str, project: str = ''):
        # Load yaml config
        config_file_path = resolve_path(config_file)
        yaml_config = yaml.load(config_file_path)
        yaml_config = {} if yaml_config is None else yaml_config  # handle empty config file
        name = config_file_path.stem
        # Handle hpsearch
        if 'hpsearch' in yaml_config:
            configs = generate_hpsearch(yaml_config, name)
        else:
            configs = {name: yaml_config}
        # Make tasks
        tasks = []
        ptype = ComputePlatformType(platform)
        for name, config in configs.items():
            t = Task(script_file=script_file, config=config, name=name, platform_type=ptype, project=project)
            t.save()  # insert in database
            tasks.append(t)
        # Submit tasks
        for t in tasks:
            ExperimentManager.submit_task(t)  # TODO submit in batch to server!

    @staticmethod
    def submit_task(task: Task):
        task.job_id = get_platform(task).submit(task)
        task.post_submit()

    @staticmethod
    def get_tasks_by_id(task_ids: list):
        return list(Task.select().where(Task.id.in_(task_ids)))

    @staticmethod
    def continue_tasks(tasks: Iterable[Task]):
        for t in tasks:
            if not t.status.is_active():
                t.job_id = get_platform(t).submit(t, continu=True)  # TODO one bulk ssh command
                t.post_continue()

    @staticmethod
    def cancel_tasks(tasks: Iterable[Task]):
        for t in tasks:
            if t.status.is_active():
                get_platform(t).cancel(t)  # TODO one bulk ssh command
                t.post_cancel()

    @staticmethod
    def monitor(t: Task):
        # TODO rename this method 'update' or something?
        t.logs = get_platform(t).fetch_logs(t)
        t.interpret_logs()

    @staticmethod
    def delete_tasks_by_id(task_ids: list):
        Task.delete().where(Task.id.in_(task_ids)).execute()

    @staticmethod
    def list_projects():
        return [t.project for t in Task.select(Task.project).where(Task.project != '').distinct()]


experiment_manager = ExperimentManager()  # FIXME do not instantiate, it is just a namespace
