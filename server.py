import time
import os
from pathlib import Path
from collections import namedtuple

import numpy as np
import pandas as pd
from ruamel_yaml import YAML
import visdom

from utils import get_item_at_path, make_html_table, make_info_tables

yaml = YAML()

CONFIGS_PATH = Path(os.environ['EM_CONFIGS_PATH'])
INFO_FIELDS = ['global.model_name', 'training.output_path', 'training.num_epochs']

Task = namedtuple('Task', ['name', 'config', 'metrics', 'best_epoch'])
Metric = namedtuple('Metric', ['name', 'type', 'data'])


class Server(object):
    def __init__(self):
        self.vis = visdom.Visdom()
        self.tasks = []
        
        if not self.vis.check_connection():
            raise RuntimeError('A visdom server must be running.')
    
    @staticmethod
    def get_metrics(config_data):
        # TODO train + val
        metrics = []
        output_path = Path(get_item_at_path(config_data, 'training.output_path'))
        
        # Loss
        losses = pd.read_csv(output_path / 'trn_losses_values.log', sep=' ', header=None, names=['ep', 'val'])
        metrics.append(
            Metric(name='Loss', type='line', data=losses.values)
        )
        best_epoch = losses['val'].idxmin()
        assert losses['ep'][best_epoch] == best_epoch
        
        # Classwise final score
        all_scores = pd.read_csv(output_path / 'trn_classes_score.log', sep=' ', header=None, names=['ep', 'id', 'val'])
        scores = all_scores[all_scores['ep'] == best_epoch].copy()
        scores['metric'], scores['class_idx'] = scores['id'].str.split('_', 1).str
        for name, val in scores.groupby('metric'):
            metrics.append(
                Metric(name=name, type='bar', data=val['val'].values)
            )
        
        return metrics, best_epoch
    
    def retrieve_task(self, config_file_path):
        config_file_path = Path(config_file_path)
        config_data = yaml.load(config_file_path)
        metrics, best_epoch = self.get_metrics(config_data)
        return Task(config_file_path.stem, config_data, metrics, best_epoch)
    
    def refresh_tasks(self):
        """
        TODO documentation
        :return: a list of Task objects.
        """

        self.tasks.clear()
        # Iterate on yaml files
        for config_file_path in CONFIGS_PATH.glob('*.yaml'):
            self.tasks.append(self.retrieve_task(config_file_path))
    
    def show_task_info(self, task):
        info = [(field_path, get_item_at_path(task.config, field_path)) for field_path in INFO_FIELDS]
        hp_params = [x['param'] for x in task.config['hpsearch']['params']]
        hpinfo = [(field_path, get_item_at_path(task.config, field_path)) for field_path in hp_params]
        all_info = {'Info': info, 'Hyperparameter search': hpinfo}
        self.vis.text(make_info_tables(all_info), win='info', env=task.name)
    
    def plot_task_metrics(self, task):
        for m in task.metrics:
            if m.type == 'line':
                self.vis.line(Y=m.data[:, 1], X=m.data[:, 0],
                              win=m.name, env=task.name, opts=dict(title=m.name))
            elif m.type == 'bar':
                rn = [str(i) for i in range(len(m.data))]
                title = m.name.capitalize() + ' for epoch ' + str(task.best_epoch)
                self.vis.bar(m.data,
                             win=m.name, env=task.name, opts=dict(title=title, rownames=rn))
    
    def main_loop(self):
        print('Experiment Manager Server is running.')
        while True:
            self.refresh_tasks()
            for task in self.tasks:
                self.show_task_info(task)
                self.plot_task_metrics(task)
            
            time.sleep(2 * 60)
    
    
if __name__ == '__main__':
    s = Server()
    s.main_loop()
