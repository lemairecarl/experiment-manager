from typing import Union

from ruamel.yaml import YAML

from hypertrainer.computeplatform import ComputePlatformType, get_platform, list_platforms
from hypertrainer.task import Task
from hypertrainer.db import get_db
from hypertrainer.hpsearch import generate as generate_hpsearch

yaml = YAML()


class ExperimentManager:
    @staticmethod
    def get_all_tasks(do_update=False):
        if do_update:
            ExperimentManager.update_statuses()
        # NOTE: statuses are requested asynchronously by the dashboard
        all_tasks = list(Task.select())
        return all_tasks

    @staticmethod
    def get_tasks(platform: ComputePlatformType):
        ExperimentManager.update_statuses(platforms=[platform])  # TODO return tasks to avoid other db query?
        tasks = Task.select().where(Task.platform_type == platform)
        for t in tasks:
            t.monitor()
        return tasks

    @staticmethod
    def update_statuses(platforms: list = None):
        if platforms is None:
            platforms = list_platforms()
        for ptype in platforms:
            platform = get_platform(ptype)
            tasks = Task.select().where(Task.platform_type == ptype)
            job_ids = [t.job_id for t in tasks]
            get_db().close()  # Close db since the following may take time
            statuses = platform.get_statuses(job_ids)
            get_db().connect()
            for t in tasks:
                if t.status.is_active():
                    t.status = statuses[t.job_id]
                    t.save()

    @staticmethod
    def submit(platform: str, script_file: str, config_file: str):
        # Load yaml config
        config_file_path = Task.resolve_path(config_file)
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
        for name, config in configs.items():
            t = Task(script_file=script_file, config=config, name=name, platform_type=ComputePlatformType(platform))
            t.save()  # insert in database
            tasks.append(t)
        # Submit tasks
        for t in tasks:
            t.submit()  # FIXME submit all at once!

    @staticmethod
    def continue_tasks(task_ids: list):
        tasks = Task.select().where(Task.id.in_(task_ids))
        for t in tasks:
            if not t.status.is_active():
                t.continu()  # TODO one bulk ssh command

    @staticmethod
    def cancel_tasks(task_ids: list):
        tasks = Task.select().where(Task.id.in_(task_ids))
        for t in tasks:
            if t.status.is_active():
                t.cancel()  # TODO one bulk ssh command

    @staticmethod
    def delete_tasks(task_ids: list):
        Task.delete().where(Task.id.in_(task_ids)).execute()


experiment_manager = ExperimentManager()
