# coding: utf-8

__author__ = 'xiayf'

import time
import functools
import smtplib
import sqlite3
import multiprocessing
from datetime import datetime
from email.mime.text import MIMEText
from email.header import Header
from collections import OrderedDict

import psutil


class DB(object):

    def __init__(self):
        self.__conn = sqlite3.connect('data.db')
        self.__cursor = self.__conn.cursor()
        self.__prepare()

    def __prepare(self):
        table_cpu = '''CREATE TABLE cpu_stat IF NOT EXIST (
            id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
            used_percent INTEGER NOT NULL DEFAULT -1,
            created_at TIMESTAMP
        )
        '''
        self.__cursor.execute(table_cpu)
        self.__conn.commit()

        table_mem = '''CREATE TABLE mem_stat IF NOT EXIST (
            id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
            used_percent INTEGER NOT NULL DEFAULT -1,
            created_at TIMESTAMP
        )
        '''
        self.__cursor.execute(table_mem)
        self.__conn.commit()

    def execute(self, sql):
        self.__cursor.execute(sql)
        self.__conn.commit()

    def query(self, sql):
        for row in self.__cursor.execute(sql):
            yield row

    def close(self):
        self.__cursor.close()
        self.__conn.close()


class CircularQueue(object):

    def __init__(self, length):
        self.__length = length
        self.__pointer = 0
        self.__queue = OrderedDict()

    def add(self, value):
        self.__queue[self.__pointer] = value
        self.__pointer = (self.__pointer + 1) % self.__length

    @property
    def data(self):
        return self.__queue.values()


class BeautyEye(object):

    def __init__(self, config):
        self.__config = config
        self.__db = DB()

    @staticmethod
    def __disk_info():
        disk_info = {}
        for dp in psutil.disk_partitions(all=False):
            # print dp.mountpoint, psutil.disk_usage(dp.mountpoint).percent, '%'
            disk_info[dp.mountpoint] = psutil.disk_usage(dp.mountpoint).percent
        return disk_info

    @staticmethod
    def __host_info():
        pass

    @staticmethod
    def __over_threshold(count, value):
        return count+1 if value >= 90 else count

    def __cpu_stat(self):
        abnormal_continue_times = 3
        cpu_stat_queue = CircularQueue(abnormal_continue_times)
        stat_interval = self.__config['cpu']['interval']
        while True:
            cpu_usage_percent = psutil.cpu_percent(1)
            # print '__cpu_stat', cpu_usage_percent, '%'

            sql = 'INSERT INTO cpu_stat (used_percent, created_at) VALUES (%d, "%s")' \
                  % (cpu_usage_percent, datetime.strftime('%Y-%m-%d %H:%M:%S'))
            self.__db.execute(sql)

            cpu_stat_queue.add(cpu_usage_percent)
            if functools.reduce(self.__over_threshold, cpu_stat_queue.data, 0) == abnormal_continue_times:
                pass

            time.sleep(stat_interval)

    def __mem_stat(self):
        abnormal_continue_times = 3
        mem_stat_queue = CircularQueue(abnormal_continue_times)
        stat_interval = self.__config['mem']['interval']
        while True:
            mem_usage = psutil.virtual_memory()
            mem_usage_percent = mem_usage.percent
            # print '__mem_stat', mem_usage_percent, '%'

            sql = 'INSERT INTO mem_stat (used_percent, created_at) VALUES (%d, "%s")' \
                  % (mem_usage_percent, datetime.strftime('%Y-%m-%d %H:%M:%S'))
            self.__db.execute(sql)

            mem_stat_queue.add(mem_usage_percent)
            if functools.reduce(self.__over_threshold, mem_stat_queue.data, 0) == abnormal_continue_times:
                pass

            time.sleep(stat_interval)

    def __disk_stat(self):
        stat_interval = self.__config['disk']['interval']
        disk_threshold = 90
        while True:
            abnormal_mountpoint = {}
            for mount_point, usage_percent in self.__disk_info().iteritems():
                if usage_percent > disk_threshold:
                    abnormal_mountpoint[mount_point] = usage_percent
            if len(abnormal_mountpoint) > 0:
                pass

            time.sleep(stat_interval)

    def __plot_data(self):
        pass

    def __render_content(self, template, data):
        content = ''
        return content

    def __prepare_data(self):
        return ''

    def __email_it(self):
        email_content = self.__prepare_data()

        msg = MIMEText(email_content, 'html', 'utf-8')
        msg['Subject'] = Header(self.__config['email']['subject'] % (datetime.strftime('%Y-%m-%d %H:%M:%S'), ), 'utf-8')
        msg['From'] = Header(self.__config['email']['from'], 'utf-8')
        msg['To'] = ', '.join(self.__config['email']['to'])

        try:
            email_server_info = self.__config['email']['server']
            s = smtplib.SMTP(email_server_info['host'], email_server_info['port'])
            s.login(email_server_info['username'], email_server_info['password'])
            s.sendmail(self.__config['email']['from'], self.__config['email']['to'], msg.as_string())
            s.quit()
        except Exception as e:
            print e
            return False
        return True

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
        },
        'email': {
            'server': {
                'host': '',
                'port': '',
                'username': '',
                'password': '',
            },
            'subject': '服务器监控数据汇总 - %s',
            'from': '',
            'to': [],
        }
    }
    be = BeautyEye(config)
    be.blink()


if __name__ == '__main__':
    main()