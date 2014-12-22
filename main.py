# coding: utf-8

__author__ = 'xiayf'

import multiprocessing
import time

import psutil


class BeautyEye(object):

    def __init__(self, config):
        print config
        self.config = config

    def __cpu_stat(self):
        stat_interval = self.config['cpu']['interval']
        while True:
            cpu_percent = psutil.cpu_percent(1)
            print '__cpu_stat', cpu_percent, '%'
            time.sleep(stat_interval)

    def __mem_stat(self):
        stat_interval = self.config['mem']['interval']
        while True:
            mem_usage = psutil.virtual_memory()
            print '__mem_stat', mem_usage.percent, '%'
            time.sleep(stat_interval)

    def __disk_stat(self):
        stat_interval = self.config['disk']['interval']
        while True:
            for dp in psutil.disk_partitions(all=False):
                print dp.mountpoint, psutil.disk_usage(dp.mountpoint).percent, '%'
            time.sleep(stat_interval)

    def blink(self):
        process_record = []
        for m in [self.__cpu_stat, self.__mem_stat, self.__disk_stat]:
            p = multiprocessing.Process(target=m)
            p.start()
            process_record.append(p)
        for p in process_record:
            p.join()


def main():
    config = {
        'cpu': {
            'interval': 1,
        },
        'mem': {
            'interval': 1,
        },
        'disk': {
            'interval': 5,
        }
    }
    be = BeautyEye(config)
    be.blink()


if __name__ == '__main__':
    main()